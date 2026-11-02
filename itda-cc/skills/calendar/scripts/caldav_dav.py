"""caldav_dav — CalDAV(WebDAV) 요청을 `cc_http` 로 직접 보낸다(서드파티 없음).

- 인증은 Basic. Authorization 헤더 값과 비밀번호는 오류 문구에 싣지 않는다(cc_http 는 URL 만 싣는다).
- PROPFIND·REPORT 의 리다이렉트는 urllib 가 따라가지 않아 여기서 한 번만 따라간다 — 같은 https 호스트 계열일 때만
  (자격증명을 엉뚱한 호스트에 보내지 않는다).
- 쓰기는 조건부다: 생성 `If-None-Match: *`, 수정·삭제 `If-Match: <etag>` — 412 는 etag_conflict.
"""
from __future__ import annotations

import base64
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import cc_http
from cal_accounts import CalAccount, CalError

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav", "a": "http://apple.com/ns/ical/"}
HTTP = cc_http.request  # 테스트가 바꾼다
TIMEOUT = 30.0


@dataclass
class Resource:
    href: str      # 절대 URL
    etag: str | None
    ics: str


def _xml(body: str) -> bytes:
    return ('<?xml version="1.0" encoding="utf-8"?>' + body).encode("utf-8")


def _same_site(a: str, b: str) -> bool:
    ha, hb = urllib.parse.urlsplit(a).hostname or "", urllib.parse.urlsplit(b).hostname or ""
    sa, sb = ".".join(ha.split(".")[-2:]), ".".join(hb.split(".")[-2:])
    return urllib.parse.urlsplit(b).scheme == "https" and sa == sb


class Dav:
    def __init__(self, account: CalAccount):
        self.account = account
        self.base = account.caldav_url
        tok = base64.b64encode(f"{account.login}:{account.password}".encode("utf-8")).decode("ascii")
        self._auth = f"Basic {tok}"
        self._secrets = (account.password or "", tok)

    # ------------------------------------------------------------ 저수준

    def request(self, method: str, url: str, *, body: bytes | None = None, depth: str | None = None,
                headers: dict | None = None, _hops: int = 0):
        hdrs = {"Authorization": self._auth}
        if body is not None:
            hdrs["Content-Type"] = ("text/calendar; charset=utf-8" if method == "PUT"
                                    else "application/xml; charset=utf-8")
        if depth is not None:
            hdrs["Depth"] = depth
        hdrs.update(headers or {})
        try:
            r = HTTP(method, url, headers=hdrs, data=body, timeout=TIMEOUT, secrets=self._secrets,
                     raise_for_status=False)
        except cc_http.HttpError as e:
            raise CalError(e.code if e.code in ("timeout", "network_error") else "network_error", str(e),
                           hint="네트워크를 확인한다. 쓰기였으면 같은 명령을 다시 보내지 말고 조회로 반영 여부부터 본다.") from None
        if r.status in (301, 302, 307, 308) and _hops < 2:
            loc = urllib.parse.urljoin(url, r.headers.get("location", ""))
            if loc and _same_site(url, loc):
                return self.request(method, loc, body=body, depth=depth, headers=headers, _hops=_hops + 1)
        if r.status == 401:
            raise CalError("auth_error", f"{self.account.login} 로그인 실패 — 앱 비밀번호가 틀렸거나 바뀌었다.",
                           hint="GUIDE.md 의 앱 비밀번호 절을 확인하고 .env 를 고친다.")
        return r

    def _multistatus(self, r, what: str) -> list:
        if r.status != 207:
            raise CalError("caldav_error", f"{what} 실패(HTTP {r.status})", status=r.status)
        try:
            root = ET.fromstring(r.body)
        except ET.ParseError:
            raise CalError("caldav_error", f"{what} 응답을 읽지 못했다(XML 아님)") from None
        return root.findall("d:response", NS)

    @staticmethod
    def _ok_props(resp) -> list:
        out = []
        for ps in resp.findall("d:propstat", NS):
            st = (ps.findtext("d:status", default="", namespaces=NS) or "")
            if " 200" in st:
                p = ps.find("d:prop", NS)
                if p is not None:
                    out.append(p)
        return out

    def _abs(self, base_url: str, href: str) -> str:
        return urllib.parse.urljoin(base_url, href)

    # ------------------------------------------------------------ 디스커버리

    def calendars(self) -> list[dict]:
        """[{id, name, components, color, url}] — VEVENT·VTODO 컬렉션."""
        body = _xml('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                    '<d:prop><d:current-user-principal/><d:resourcetype/></d:prop></d:propfind>')
        r = self.request("PROPFIND", self.base, body=body, depth="0")
        principal, is_cal = None, False
        for resp in self._multistatus(r, "PROPFIND(principal)"):
            for p in self._ok_props(resp):
                h = p.find("d:current-user-principal/d:href", NS)
                if h is not None and h.text:
                    principal = self._abs(self.base, h.text.strip())
                if p.find("d:resourcetype/c:calendar", NS) is not None:
                    is_cal = True
        if is_cal:
            return self._list_collections(self.base, depth="0")
        home = self.base
        if principal:
            body = _xml('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                        '<d:prop><c:calendar-home-set/></d:prop></d:propfind>')
            r = self.request("PROPFIND", principal, body=body, depth="0")
            for resp in self._multistatus(r, "PROPFIND(calendar-home-set)"):
                for p in self._ok_props(resp):
                    h = p.find("c:calendar-home-set/d:href", NS)
                    if h is not None and h.text:
                        home = self._abs(principal, h.text.strip())
        return self._list_collections(home, depth="1")

    def _list_collections(self, url: str, depth: str) -> list[dict]:
        body = _xml('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:a="http://apple.com/ns/ical/">'
                    '<d:prop><d:displayname/><d:resourcetype/><c:supported-calendar-component-set/>'
                    '<a:calendar-color/></d:prop></d:propfind>')
        r = self.request("PROPFIND", url, body=body, depth=depth)
        out = []
        for resp in self._multistatus(r, "PROPFIND(calendars)"):
            href = resp.findtext("d:href", default="", namespaces=NS).strip()
            name, comps, color, is_cal = None, [], None, False
            for p in self._ok_props(resp):
                if p.find("d:resourcetype/c:calendar", NS) is not None:
                    is_cal = True
                name = name or (p.findtext("d:displayname", default="", namespaces=NS) or "").strip() or None
                comps += [c.get("name") for c in p.findall("c:supported-calendar-component-set/c:comp", NS) if c.get("name")]
                color = color or (p.findtext("a:calendar-color", default="", namespaces=NS) or "").strip() or None
            if not is_cal:
                continue
            full = self._abs(url, href)
            cid = urllib.parse.unquote(full.rstrip("/").rsplit("/", 1)[-1])
            out.append({"id": cid, "name": name or cid, "components": comps or ["VEVENT"], "color": color, "url": full})
        return out

    # ------------------------------------------------------------ 일정 읽기

    def query(self, cal_url: str, start_utc: str, end_utc: str, expand: bool) -> list[Resource]:
        exp = f'<c:expand start="{start_utc}" end="{end_utc}"/>' if expand else ""
        body = _xml('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                    f'<d:prop><d:getetag/><c:calendar-data>{exp}</c:calendar-data></d:prop>'
                    '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
                    f'<c:time-range start="{start_utc}" end="{end_utc}"/>'
                    '</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
        r = self.request("REPORT", cal_url, body=body, depth="1")
        return self._resources(cal_url, self._multistatus(r, "REPORT(calendar-query)"))

    def all_objects(self, cal_url: str) -> list[Resource]:
        """서버가 time-range REPORT 를 비워 돌려주는 경우(네이버)용 — 목록을 받아 multiget 으로 읽는다."""
        body = _xml('<d:propfind xmlns:d="DAV:"><d:prop><d:getetag/><d:resourcetype/></d:prop></d:propfind>')
        r = self.request("PROPFIND", cal_url, body=body, depth="1")
        hrefs = []
        base_path = urllib.parse.urlsplit(cal_url).path.rstrip("/")
        for resp in self._multistatus(r, "PROPFIND(objects)"):
            href = resp.findtext("d:href", default="", namespaces=NS).strip()
            full = self._abs(cal_url, href)
            if urllib.parse.urlsplit(full).path.rstrip("/") == base_path:
                continue
            if any(p.find("d:resourcetype/d:collection", NS) is not None for p in self._ok_props(resp)):
                continue
            hrefs.append(href)
        out: list[Resource] = []
        for i in range(0, len(hrefs), 100):
            chunk = hrefs[i:i + 100]
            body = _xml('<c:calendar-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                        '<d:prop><d:getetag/><c:calendar-data/></d:prop>'
                        + "".join(f"<d:href>{_esc(h)}</d:href>" for h in chunk) + "</c:calendar-multiget>")
            r = self.request("REPORT", cal_url, body=body, depth="1")
            if r.status == 207:
                out += self._resources(cal_url, self._multistatus(r, "REPORT(multiget)"))
            else:
                for h in chunk:
                    res = self.get(self._abs(cal_url, h))
                    if res is not None:
                        out.append(res)
        return out

    def find_uid(self, cal_url: str, uid: str) -> Resource | None:
        body = _xml('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                    '<d:prop><d:getetag/><c:calendar-data/></d:prop>'
                    '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
                    f'<c:prop-filter name="UID"><c:text-match collation="i;octet">{_esc(uid)}</c:text-match>'
                    '</c:prop-filter></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
        r = self.request("REPORT", cal_url, body=body, depth="1")
        cands = self._resources(cal_url, self._multistatus(r, "REPORT(uid)")) if r.status == 207 else []
        if not cands:
            cands = self.all_objects(cal_url)  # UID REPORT 를 거부·무시하는 서버(iCloud 412·네이버 빈 응답)
        import ical_min
        for res in cands:
            try:
                cal = ical_min.parse(res.ics)
            except ValueError:
                continue
            if any(ev.text("UID") == uid for ev in ical_min.vevents(cal)):
                got = self.get(res.href)  # GET 으로 최신 원문 전체
                if got is None:
                    return res
                if not got.etag:
                    # 네이버는 GET 응답에 ETag 헤더를 싣지 않는다(2026-11-02 라이브) — PROPFIND getetag 로 받는다.
                    got = Resource(got.href, self.propfind_etag(got.href) or res.etag, got.ics)
                return got
        return None

    def get(self, href: str) -> Resource | None:
        r = self.request("GET", href)
        if r.status == 404:
            return None
        if not (200 <= r.status < 300):
            raise CalError("caldav_error", f"GET 실패(HTTP {r.status})", status=r.status)
        return Resource(href, r.headers.get("etag"), r.body.decode("utf-8", "replace"))

    def propfind_etag(self, href: str) -> str | None:
        """한 리소스의 getetag(Depth 0). GET 헤더에 ETag 가 없는 서버(네이버)용."""
        body = _xml('<d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>')
        r = self.request("PROPFIND", href, body=body, depth="0")
        if r.status != 207:
            return None
        for resp in self._multistatus(r, "PROPFIND(etag)"):
            for pr in self._ok_props(resp):
                e = (pr.findtext("d:getetag", default="", namespaces=NS) or "").strip()
                if e:
                    return e
        return None

    def _resources(self, base_url: str, responses) -> list[Resource]:
        out = []
        for resp in responses:
            href = resp.findtext("d:href", default="", namespaces=NS).strip()
            for p in self._ok_props(resp):
                data = p.findtext("c:calendar-data", default=None, namespaces=NS)
                if data:
                    etag = (p.findtext("d:getetag", default="", namespaces=NS) or "").strip() or None
                    out.append(Resource(self._abs(base_url, href), etag, data))
        return out

    # ------------------------------------------------------------ 쓰기

    def put(self, href: str, ics: str, *, etag: str | None) -> str | None:
        hdrs = {"If-Match": etag} if etag else {"If-None-Match": "*"}
        r = self.request("PUT", href, body=ics.encode("utf-8"), headers=hdrs)
        if r.status == 412:
            raise CalError("etag_conflict", "조회 뒤 다른 곳에서 일정이 바뀌었다(또는 같은 uid 가 이미 있다).",
                           hint="get 으로 다시 조회해 바뀐 내용을 사용자에게 보여 주고 확인받는다.")
        if r.status not in (200, 201, 204):
            raise CalError("caldav_error", f"PUT 실패(HTTP {r.status})", status=r.status)
        new = r.headers.get("etag")
        if not new:
            got = self.get(href)
            new = got.etag if got else None
        if not new:
            new = self.propfind_etag(href)
        return new

    def delete(self, href: str, *, etag: str) -> None:
        r = self.request("DELETE", href, headers={"If-Match": etag})
        if r.status == 412:
            raise CalError("etag_conflict", "지우는 순간 일정이 바뀌어 있었다 — 지우지 않았다.",
                           hint="delete 를 --confirm 없이 다시 실행해 새 미리보기를 보여 주고 다시 승인받는다.")
        if r.status == 404:
            raise CalError("not_found", "일정이 이미 없다.")
        if r.status not in (200, 204):
            raise CalError("caldav_error", f"DELETE 실패(HTTP {r.status})", status=r.status)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

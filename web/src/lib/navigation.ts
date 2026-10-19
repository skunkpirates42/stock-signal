const SECTIONS_WITH_DETAIL_PAGES = ["/research", "/runs"];

export function isActiveRailLink(pathname: string, href: string): boolean {
  if (pathname === href) return true;
  return SECTIONS_WITH_DETAIL_PAGES.includes(href) && pathname.startsWith(`${href}/`);
}

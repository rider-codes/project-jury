// Where a visitor without an access code can ask for one. Set NEXT_PUBLIC_REQUEST_CODE_URL
// (a mailto: or a form link) to change it; the default opens an issue on the project's repo.
export const REQUEST_CODE_URL =
  process.env.NEXT_PUBLIC_REQUEST_CODE_URL ??
  "https://github.com/rider-codes/project-jury/issues/new?title=Access+code+request";

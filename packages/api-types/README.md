# @maapmitra/api-types

TypeScript types generated from the FastAPI OpenAPI schema; shared by `frontend/` and `mobile/`.
After any backend schema change: `cd packages/api-types && npm install && npm run gen`, then commit
`openapi.json` and `schema.d.ts`. Never edit `schema.d.ts` by hand.

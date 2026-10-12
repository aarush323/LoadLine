# Loadline marketing site

Vite + React + TypeScript + Tailwind 4. Shadcn-style layout: UI primitives live in `src/components/ui/` (see `components.json`).

## Develop

```bash
cd website
npm install
npm run dev
```

Hero uses **UnicornStudio** on large screens (`src/components/ui/hero-ascii-one.tsx`). Requires network on first load for the CDN script.

## shadcn (optional)

Project is already on Tailwind + TS. To add more shadcn components:

```bash
cd website
npx shadcn@latest init   # accepts existing components.json
npx shadcn@latest add button
```

The `@/` alias points at `src/` (`vite.config.ts` + `tsconfig.json`).

## Vercel

Root Directory: `website`. Build: `npm run build`. Output: `dist`.

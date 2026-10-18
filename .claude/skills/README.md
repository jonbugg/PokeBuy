# Design skills

Third-party agent skills added for design and polish work on Dreamscrol.

| Skill | Source | Version | License |
|---|---|---|---|
| `impeccable` | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 4.6.0 (commit 2f46b7a) | Apache-2.0 (`impeccable/LICENSE`) |
| `design-taste-frontend` (Taste Skill v2) | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | commit a9c73c3 | MIT (`design-taste-frontend/LICENSE`) |
| `emil-design-eng`, `animate`, `animate-expo`, `review-animations`, `improve-animations`, `find-animation-opportunities`, `animation-performance`, `animation-vocabulary`, `apple-design`, `mobile-native`, `break-ui`, `prototype`, `pick-ui-library`, `ask-sonner`, `write-swift` | [emilkowalski/skill](https://github.com/emilkowalski/skill) | commit 2d22863 | MIT (`EMIL-KOWALSKI-LICENSE`) |

Impeccable's `scripts/` folder is not included. Its launcher downloads and runs a prebuilt binary (the anti-pattern detector, live browser mode and critique storage). The skill's written guidance works without it and falls back to reading project context directly. For the full version on your own machine, install the plugin with `/plugin marketplace add pbakaus/impeccable` in Claude Code.

Taste Skill's `scripts/` and `assets/` folders (Node scripts that deal design directions and inspect pages in Chrome) are also left out. Its rules, references and direction library are included; for app screens read `design-taste-frontend/references/app-screens.md`.

To update, re-copy the skill folders from the source repos and bump the versions above.

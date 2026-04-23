# Image Generation Workflow (Nano Banana)

This repository uses generated visuals for architecture documentation and article assets.

## Recommended Skill Mapping

- Claude Code plugin reference package: `tools/image-generator-openai/`
- Codex skill to use: `image-generator`

For Codex, invoke image generation requests using the installed `image-generator` skill (Gemini Nano Banana Pro backend).

## Asset Rules

- Save generated outputs in `docs/assets/`.
- Prefer descriptive file names: `agentcore-<topic>-<view>.png`.
- Keep source prompts in PR notes or internal docs, not in secrets-bearing files.

## Quality Guidelines

- Use high-contrast diagrams for technical readability.
- Keep labels concise and consistent with architecture terminology.
- Regenerate images when architecture boundaries change (Runtime/Gateway/Identity/Providers).

## Safety

- Do not include real account IDs, emails, access tokens, or profile names in prompts.
- Sanitize all generated visuals before publishing.

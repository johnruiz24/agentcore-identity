# OpenAI Image Generator Plugin

Generate and edit images using OpenAI's **gpt-image-2** model (ChatGPT Images 2.0, released April 21, 2026).

## Features

- **Text-to-Image Generation**: Create high-quality images from text descriptions
- **Image Editing**: Modify existing images with natural language prompts
- **Multiple Sizes**: Square (1024x1024), Landscape (1792x1024), Portrait (1024x1792)
- **Quality Options**: Standard (faster) or HD (higher detail)
- **Style Control**: Vivid (hyper-realistic) or Natural (less processed)

## Setup

### 1. Get an OpenAI API Key

1. Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Click "Create new secret key"
3. Copy your API key

### 2. Set Environment Variable

Add to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):

```bash
export OPENAI_API_KEY="your_api_key_here"
```

Then restart your terminal or run:

```bash
source ~/.zshrc  # or ~/.bashrc
```

**IMPORTANT:** The plugin will not work without this API key configured.

## Usage

### Text-to-Image Generation

Simply ask Claude to generate an image:

```
Generate an image of a fox in Lisbon at sunset, cinematic style
```

```
Create a technical diagram showing a four-layer architecture with Runtime, Gateway, Identity, and Provider layers
```

```
Generate a minimalist logo for a coffee shop called "The Daily Grind"
```

### Image Editing

Provide an image path and describe the edit:

```
Edit the image at ./photo.png and add a wizard hat to the person
```

```
Take the image at input.jpg and change the background to a sunset beach
```

### Parameters

Claude will automatically use appropriate defaults, but you can specify:

- **Size**: "Generate a 1792x1024 landscape image..."
- **Quality**: "Generate a high-detail (HD) image..."
- **Style**: "Generate a vivid, dramatic image..." or "Generate a natural-looking image..."

## Prompting Best Practices

### 1. Be Descriptive

❌ Bad: `cat, wizard hat, cute`  
✅ Good: `A fluffy orange cat wearing a small knitted wizard hat, sitting on a wooden floor with soft natural lighting from a window`

### 2. Specify Style and Mood

- Photography terms: "shot with 85mm lens", "soft bokeh background", "golden hour lighting"
- Artistic styles: "in the style of Van Gogh", "minimalist illustration", "photorealistic"
- Mood: "warm and cozy atmosphere", "dramatic noir lighting"

### 3. For Technical Diagrams

- Mention specific elements: "four-layer stack", "data flow arrows", "isometric 3D blocks"
- Specify colors: "dark background with cyan accents", "color-coded layers"
- Request labels: "labeled components", "annotations showing data flow"

### 4. For Text in Images

Be explicit about:
- The exact text to render: "text should read: 'AgentCore Runtime'"
- Font style (descriptively): "clean, bold, sans-serif font"
- Placement: "centered at top", "as a banner"

### 5. For Product/Commercial Images

- Lighting setup: "three-point softbox lighting"
- Background: "clean white studio background"
- Camera angle: "slightly elevated 45-degree shot"

## Capabilities

### Model: gpt-image-2

**ChatGPT Images 2.0** (launched April 2026) offers:
- Improved text rendering in images
- Better prompt understanding (GPT-based architecture)
- Native editing support
- Advanced style control

### Supported Sizes

- `1024x1024` - Square (default)
- `1792x1024` - Landscape (wide)
- `1024x1792` - Portrait (tall)

### Quality Levels

- `standard` - Faster generation, good quality (default)
- `hd` - Higher detail, slower, better for complex scenes

### Style Options

- `vivid` - Hyper-realistic, dramatic, high contrast
- `natural` - More natural-looking, less processed

### Response Format

The plugin uses `b64_json` format for direct image data (no separate download step needed).

## Rate Limits

OpenAI rate limits vary by tier:
- **Tier 1**: ~5 images/minute
- **Tier 2**: ~50 images/minute  
- **Tier 3**: ~200 images/minute

Check your current limits at: https://platform.openai.com/account/rate-limits

## Troubleshooting

### "ERROR: OPENAI_API_KEY is not set"

**Solution:** Export the API key in your shell profile:

```bash
export OPENAI_API_KEY="sk-proj-..."
```

Then restart your terminal or run `source ~/.zshrc`.

### "401 Unauthorized"

**Causes:**
- API key is invalid or expired
- API key wasn't properly exported

**Solution:**
1. Verify your API key at https://platform.openai.com/api-keys
2. Re-export with the correct key
3. Restart Claude Code

### "429 Rate Limit Exceeded"

**Cause:** You've hit your rate limit

**Solution:**
- Wait a few minutes before trying again
- Upgrade your OpenAI tier for higher limits
- Check usage at https://platform.openai.com/usage

### "400 Bad Request: Invalid size"

**Cause:** Requested size is not supported

**Solution:** Use one of the supported sizes:
- 1024x1024
- 1792x1024
- 1024x1792

## Comparison: gpt-image-2 vs DALL-E 3

| Feature | DALL-E 3 | gpt-image-2 |
|---------|----------|-------------|
| Model Family | DALL-E | GPT Image |
| Launch Date | September 2023 | April 2026 |
| Text Rendering | Limited | Improved |
| Prompt Understanding | Good | Better (GPT-based) |
| Editing Support | Via separate endpoint | Native |
| Style Control | Basic | Advanced |

**Key advantages of gpt-image-2:**
- Better understanding of complex prompts
- Improved text rendering for logos, diagrams, infographics
- Native editing workflow
- Can integrate with GPT-5.4 for multi-tool workflows

## Technical Details

**API Endpoint:** `https://api.openai.com/v1/images/generations`  
**Model ID:** `gpt-image-2`  
**Authentication:** Bearer token via `OPENAI_API_KEY`  
**Response Format:** Base64 JSON (no temporary URLs)

## Examples

### Example 1: Architecture Diagram

**Prompt:**
```
Generate a technical diagram showing a four-layer architecture stack as glowing 3D isometric blocks: 
- Top: "AgentCore Runtime" (purple)
- Second: "Gateway MCP" (cyan)  
- Third: "Identity Service" (green)
- Bottom: "Providers" (orange)
Dark background, glowing connection arrows, professional style
```

### Example 2: Product Photography

**Prompt:**
```
A high-resolution, studio-lit product photograph of a minimalist ceramic coffee mug in matte black on a polished concrete surface. Three-point softbox lighting with soft, diffused highlights. Slightly elevated 45-degree camera angle. Sharp focus.
```

### Example 3: Logo Design

**Prompt:**
```
Create a modern, minimalist logo for a tech company called "AgentCore". The text should be in a clean, bold, sans-serif font. Use a color scheme of dark blue and cyan. Include a subtle icon representing connected nodes or a network. Square format, suitable for app icons.
```

## Version

**Plugin Version:** 1.0.0  
**Model:** gpt-image-2 (ChatGPT Images 2.0)  
**Last Updated:** April 2026

## Author

Created by Claude (Sonnet 4.5)

## License

This plugin is provided as-is for use with Claude Code.

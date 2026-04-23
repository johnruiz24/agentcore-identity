---
name: OpenAI Image Generator
description: Generate and edit images using OpenAI's gpt-image-2 model (ChatGPT Images 2.0). Use this skill when the user asks you to generate images using OpenAI, create visuals with ChatGPT Images 2.0, edit photos, create logos, generate diagrams, or perform any image generation/editing task with the latest OpenAI model.
allowed-tools: Read, Write, Bash
---

# OpenAI Image Generator

This skill generates and edits images using OpenAI's **gpt-image-2** model (ChatGPT Images 2.0, released April 21, 2026).

## IMPORTANT: Setup Required

Before using this skill, the user must set the `OPENAI_API_KEY` environment variable:

1. Get an API key from [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Export the key in your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):
   ```bash
   export OPENAI_API_KEY="your_api_key_here"
   ```
3. Restart your terminal or run `source ~/.zshrc` (or `~/.bashrc`)

**The skill will not work without this configuration.**

## Pre-flight Check

Before making any API call, verify the key is set:

```bash
if [ -z "$OPENAI_API_KEY" ]; then
  echo "ERROR: OPENAI_API_KEY is not set. Please export it in your shell profile."
  exit 1
fi
```

If the key is missing, stop and tell the user to set it using the instructions above.

## Configuration

**Model**: `gpt-image-2` (ChatGPT Images 2.0)

**API Endpoint**: `https://api.openai.com/v1/images/generations`

**API Key**: Read from the `OPENAI_API_KEY` environment variable

**Authentication**: Bearer token in Authorization header

## Text-to-Image Generation

### Basic Generation Workflow

```bash
# Pre-flight check
if [ -z "$OPENAI_API_KEY" ]; then
  echo "ERROR: OPENAI_API_KEY is not set"
  echo "Set it in your shell profile: export OPENAI_API_KEY='your-key-here'"
  exit 1
fi

# User's prompt
PROMPT="A cinematic photo of a fox in Lisbon at sunset"
SIZE="1024x1024"  # Options: 1024x1024, 1792x1024, 1024x1792
QUALITY="standard"  # Options: standard, hd
STYLE="vivid"  # Options: vivid, natural

# Write request to file (avoids command-line length limits)
cat > /tmp/openai_request.json << JSONEOF
{
  "model": "gpt-image-2",
  "prompt": "${PROMPT}",
  "size": "${SIZE}",
  "quality": "${QUALITY}",
  "style": "${STYLE}",
  "response_format": "b64_json",
  "n": 1
}
JSONEOF

# Call OpenAI API
curl -s -X POST https://api.openai.com/v1/images/generations \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/openai_request.json > /tmp/openai_response.json

# Check for errors
if grep -q '"error"' /tmp/openai_response.json; then
  ERROR_MSG=$(python3 -c "import json, sys; data=json.load(open('/tmp/openai_response.json')); print(data.get('error', {}).get('message', 'Unknown error'))" 2>/dev/null || echo "API request failed")
  echo "❌ OpenAI API Error: $ERROR_MSG"
  exit 1
fi

# Extract and save image
python3 -c "
import json, base64, sys

try:
    with open('/tmp/openai_response.json') as f:
        data = json.load(f)
    
    if 'data' not in data or len(data['data']) == 0:
        print('❌ Error: No image data in response', file=sys.stderr)
        sys.exit(1)
    
    img_data = data['data'][0]['b64_json']
    
    with open('generated_image.png', 'wb') as f:
        f.write(base64.b64decode(img_data))
    
    print('✓ Image saved: generated_image.png')
    
except KeyError as e:
    print(f'❌ Error: Missing key in response: {e}', file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f'❌ Error extracting image: {e}', file=sys.stderr)
    sys.exit(1)
"
```

### Supported Parameters

#### Size Options

- `1024x1024` - Square (default, good for general use)
- `1792x1024` - Landscape (wide format)
- `1024x1792` - Portrait (tall format)

#### Quality Options

- `standard` - Faster generation, good quality (default)
- `hd` - Higher detail, slower, better for complex scenes

#### Style Options

- `vivid` - Hyper-realistic, dramatic, high contrast
- `natural` - More natural-looking, less processed (default)

### Complete Example: Generate Technical Diagram

```bash
# Pre-flight check
if [ -z "$OPENAI_API_KEY" ]; then
  echo "ERROR: OPENAI_API_KEY is not set"
  exit 1
fi

# Technical diagram prompt
PROMPT="Professional technical diagram showing a four-layer architecture stack as glowing 3D isometric blocks floating in dark space. Top layer labeled 'AgentCore Runtime' (purple), second layer 'Gateway MCP' (cyan), third layer 'Identity Service' (green), bottom layer 'Providers' (orange). Bright cyan data flow arrows connecting layers vertically. Dark background with subtle grid pattern. High-tech, clean lines, professional enterprise architecture style."

SIZE="1792x1024"  # Landscape for diagram
QUALITY="hd"  # High detail for technical content
STYLE="vivid"  # Dramatic for presentation

# Create request
cat > /tmp/openai_request.json << JSONEOF
{
  "model": "gpt-image-2",
  "prompt": "${PROMPT}",
  "size": "${SIZE}",
  "quality": "${QUALITY}",
  "style": "${STYLE}",
  "response_format": "b64_json",
  "n": 1
}
JSONEOF

# Call API
curl -s -X POST https://api.openai.com/v1/images/generations \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/openai_request.json > /tmp/openai_response.json

# Extract image
python3 -c "
import json, base64, sys

try:
    with open('/tmp/openai_response.json') as f:
        data = json.load(f)
    
    if 'data' not in data or len(data['data']) == 0:
        print('❌ Error: No image data in response', file=sys.stderr)
        sys.exit(1)
    
    img_data = data['data'][0]['b64_json']
    
    with open('architecture_diagram.png', 'wb') as f:
        f.write(base64.b64decode(img_data))
    
    print('✓ Technical diagram saved: architecture_diagram.png')
    
except KeyError as e:
    print(f'❌ Error: Missing key in response: {e}', file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f'❌ Error extracting image: {e}', file=sys.stderr)
    sys.exit(1)
"
```

## Image Editing

When the user provides a path to an existing image and wants to edit it, use the `/images/edits` endpoint.

### Image Editing Workflow

```bash
# Pre-flight check
if [ -z "$OPENAI_API_KEY" ]; then
  echo "ERROR: OPENAI_API_KEY is not set"
  exit 1
fi

# User provides image path and edit request
IMG_PATH="input.png"
EDIT_PROMPT="Add a wizard hat to the person in this image"
SIZE="1024x1024"

# Verify image exists
if [ ! -f "$IMG_PATH" ]; then
  echo "❌ Error: Image not found at $IMG_PATH"
  exit 1
fi

# Call editing API (uses multipart form data)
curl -s -X POST https://api.openai.com/v1/images/edits \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F image=@"$IMG_PATH" \
  -F prompt="$EDIT_PROMPT" \
  -F model="gpt-image-2" \
  -F size="$SIZE" \
  -F response_format="b64_json" > /tmp/openai_edit_response.json

# Check for errors
if grep -q '"error"' /tmp/openai_edit_response.json; then
  ERROR_MSG=$(python3 -c "import json; data=json.load(open('/tmp/openai_edit_response.json')); print(data.get('error', {}).get('message', 'Unknown error'))" 2>/dev/null || echo "API request failed")
  echo "❌ OpenAI API Error: $ERROR_MSG"
  exit 1
fi

# Extract edited image
python3 -c "
import json, base64, sys

try:
    with open('/tmp/openai_edit_response.json') as f:
        data = json.load(f)
    
    img_data = data['data'][0]['b64_json']
    
    with open('edited_image.png', 'wb') as f:
        f.write(base64.b64decode(img_data))
    
    print('✓ Edited image saved: edited_image.png')
    
except Exception as e:
    print(f'❌ Error extracting edited image: {e}', file=sys.stderr)
    sys.exit(1)
"
```

### Editing vs Generation

| Operation | Endpoint | Use Case |
|-----------|----------|----------|
| **Generation** | `/images/generations` | Create new image from text prompt |
| **Editing** | `/images/edits` | Modify existing image with prompt |

**Key difference:** Editing requires an input image file and uses multipart form data (`-F` flags in curl), while generation only needs a JSON prompt.

## Error Handling

### Common Errors

#### 1. Missing API Key

```bash
if [ -z "$OPENAI_API_KEY" ]; then
  echo "ERROR: OPENAI_API_KEY is not set"
  echo "Please add to your shell profile:"
  echo "export OPENAI_API_KEY='your-key-here'"
  exit 1
fi
```

#### 2. Invalid API Response

```bash
# Always check for error field in response
if grep -q '"error"' /tmp/openai_response.json; then
  ERROR_MSG=$(python3 -c "import json; print(json.load(open('/tmp/openai_response.json'))['error']['message'])")
  echo "❌ API Error: $ERROR_MSG"
  exit 1
fi
```

#### 3. Rate Limit Exceeded

If you see "429 Rate Limit Exceeded":
- Wait a few minutes before retrying
- Check your tier limits at https://platform.openai.com/account/rate-limits
- Consider upgrading your tier for higher limits

#### 4. Invalid Size Parameter

Only these sizes are supported:
- 1024x1024
- 1792x1024  
- 1024x1792

Using any other size will result in a 400 error.

## Prompting Best Practices

### For Better Results

1. **Be Descriptive**: Instead of "cat with hat", use "A fluffy orange cat wearing a small knitted wizard hat, sitting on a wooden floor with soft natural lighting"

2. **Specify Style**: Add terms like "photorealistic", "minimalist illustration", "in the style of Van Gogh", "cinematic lighting"

3. **For Technical Content**: Mention specific elements like "isometric 3D", "dark background with cyan accents", "labeled components", "data flow arrows"

4. **For Text in Images**: Be explicit about exact text and font style: "bold sans-serif text reading 'AgentCore Runtime'"

5. **For Products**: Specify lighting setup: "three-point softbox lighting", camera angle: "45-degree elevated shot"

## Model Capabilities

**gpt-image-2** (ChatGPT Images 2.0) offers:

- ✅ Improved text rendering in images (logos, diagrams, infographics)
- ✅ Better prompt understanding (GPT-based architecture)
- ✅ Native editing support
- ✅ Advanced style control (vivid/natural)
- ✅ Multiple aspect ratios
- ✅ Quality settings (standard/hd)

**Comparison with DALL-E 3:**
- Better prompt understanding (uses GPT architecture)
- Improved text rendering
- Native editing workflow
- Can integrate with GPT-5.4 for complex multi-tool workflows

## Rate Limits

Typical OpenAI rate limits (check your tier):
- **Tier 1**: ~5 images/minute
- **Tier 2**: ~50 images/minute
- **Tier 3**: ~200 images/minute

Check current limits: https://platform.openai.com/account/rate-limits

## Response Format

The plugin uses `response_format: "b64_json"` for direct base64 image data. This avoids the need for a separate download step and doesn't require handling temporary URLs that expire after 1 hour.

Alternative: `response_format: "url"` returns a temporary URL, but requires an additional curl download step.

## Important Notes

- All generated images include watermarking per OpenAI's policies
- Images are not stored by the API - save outputs locally
- For best text rendering, use descriptive font style terms rather than specific font names
- HD quality is slower but produces better results for complex scenes
- Vivid style tends to be more dramatic/hyper-realistic than natural style

## Troubleshooting

### Image Not Generated

1. Check API key is set: `echo $OPENAI_API_KEY`
2. Verify API key is valid at https://platform.openai.com/api-keys
3. Check response file: `cat /tmp/openai_response.json`
4. Look for error field in JSON response

### Poor Quality Results

- Try `quality: "hd"` for better detail
- Use more descriptive prompts
- Specify style, lighting, and mood explicitly
- For technical content, mention specific visual elements

### Text Not Rendering Well

- Use descriptive terms: "bold sans-serif font" instead of "Arial"
- Keep text short and clear in the prompt
- Specify text placement: "centered at top", "as a banner"
- gpt-image-2 has improved text rendering vs DALL-E 3, but still has limits

## Version

**Model**: gpt-image-2  
**Release Date**: April 21, 2026  
**Plugin Version**: 1.0.0

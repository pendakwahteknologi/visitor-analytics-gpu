# Gender Detection for Malaysian Demographics

## Overview

This system uses **DeepFace** library for gender classification, optimized for Malaysian demographics including:
- **Malay** (with and without hijab/headscarf)
- **Chinese**
- **Indian**
- **Other ethnicities**

## How It Works

### Facial Feature Analysis

DeepFace focuses on **facial features** rather than hair or clothing, making it effective for:

✓ **Hijab/Headscarf Detection**: Works because it analyzes face shape, facial structure, and expressions
✓ **Multi-Ethnic Support**: Trained on diverse datasets including Asian faces
✓ **Cultural Clothing**: Not affected by traditional clothing or accessories

### Technical Implementation

**Model**: DeepFace with OpenCV detector backend
**Focus Areas**:
- Face shape and structure
- Facial features (eyes, nose, mouth)
- Facial proportions
- Expression patterns

**NOT Used** (making it hijab-compatible):
- Hair length or style
- Head covering
- Clothing or accessories

## Configuration

### Settings in `.env`

```bash
# Enable/disable gender detection
GENDER_ENABLED=false

# Confidence threshold (0.0 - 1.0)
# Higher = more strict, fewer classifications
# Lower = more permissive, more classifications
GENDER_THRESHOLD=0.6
```

### Runtime Settings

Gender detection can be toggled via:
1. **Web UI**: Check "Enable Gender Detection" checkbox
2. **API**: `POST /settings` with `{"enable_gender": true}`

## Performance Optimization

### Detection Intervals

To maintain good FPS:
- **Person Detection**: Every 2 frames (~7.5 times/sec at 15 FPS)
- **Gender Classification**: Every 5 frames (~3 times/sec at 15 FPS)

This balance ensures:
- Smooth video stream
- Accurate people counting
- Reliable gender classification

### Why Gender is Slower

Gender classification is computationally expensive because it requires:
1. Face detection within person bounding box
2. Face alignment and preprocessing
3. Deep neural network inference
4. Confidence calculation

Running it every frame would reduce FPS from 15 to ~5-8.

## Accuracy Considerations

### High Accuracy Scenarios

✓ Front-facing individuals
✓ Good lighting conditions
✓ Clear facial features visible
✓ Distance: 1-10 meters from camera

### Lower Accuracy Scenarios

⚠ Side profile or back view
⚠ Poor lighting (too dark/bright)
⚠ Face obscured (mask, hand)
⚠ Too far from camera (>15 meters)
⚠ Very fast movement (motion blur)

### Hijab Handling

**Works Well**:
- Hijab covering hair but face visible
- Niqab with eyes visible
- Traditional Malay headscarves
- Chinese/Indian cultural headwear

**May Return "Unknown"**:
- Full face covering (burqa)
- Face turned away
- Sunglasses + mask combination

## Understanding Results

### Gender Labels

- **Male**: Detected as male with confidence > 60%
- **Female**: Detected as female with confidence > 60%
- **Unknown**:
  - Confidence below 60%
  - Face not detected
  - Side/back view
  - Face obscured

### Confidence Threshold

The `GENDER_THRESHOLD=0.6` means:
- Only classifications with 60%+ confidence are shown
- Below 60% = labeled as "Unknown"
- Adjustable based on your preference:
  - `0.5` = More classifications, some incorrect
  - `0.7` = Fewer classifications, more accurate
  - `0.8` = Very strict, high accuracy

## Statistics

### Live Stats (Current Frame)
- **People Count**: Current number of people
- **Male**: Current male count
- **Female**: Current female count

### Session Stats (Cumulative)
- **Total Detected**: Sum of all detections across frames
- **Male Detected**: Sum of male detections
- **Female Detected**: Sum of female detections

**Note**: Session stats are frame-based, not unique person counts.

## Usage Examples

### Enable Gender Detection

**Via Web UI:**
1. Open http://10.0.50.203:8000
2. Check "Enable Gender Detection"
3. Start stream

**Via API:**
```bash
curl -X POST http://10.0.50.203:8000/settings \
  -H "Content-Type: application/json" \
  -d '{"enable_gender": true}'
```

### Adjust Confidence Threshold

Edit `.env`:
```bash
# More strict (fewer classifications, higher accuracy)
GENDER_THRESHOLD=0.7

# More permissive (more classifications, may have errors)
GENDER_THRESHOLD=0.5
```

Restart server after changing.

## Performance Impact

| Setting | FPS | CPU Usage | Accuracy |
|---------|-----|-----------|----------|
| Gender OFF | 15 | Medium | N/A |
| Gender ON (every 5 frames) | 12-15 | Medium-High | Good |
| Gender ON (every 2 frames) | 8-10 | High | Better |

**Recommendation**: Keep at every 5 frames for balanced performance.

## Privacy & Ethics

### Considerations

1. **Consent**: Ensure proper signage informing people of gender detection
2. **Data Storage**: Currently not stored; only real-time analysis
3. **Accuracy Limitations**: Not 100% accurate, should not be used for critical decisions
4. **Cultural Sensitivity**: Works across cultures but respects privacy with hijab/headscarf

### Best Practices

- Use for statistical purposes only
- Do not use for individual identification
- Respect local privacy laws (PDPA in Malaysia)
- Provide opt-out mechanisms if required
- Regular accuracy audits

## Troubleshooting

### "Unknown" for Most People

**Causes**:
- Threshold too high
- Poor camera angle (side view)
- Low light conditions
- People too far from camera

**Solutions**:
- Lower `GENDER_THRESHOLD` to 0.5
- Adjust camera position for front views
- Improve lighting
- Position camera closer

### Low FPS After Enabling Gender

**Causes**:
- Running on CPU (no GPU)
- Gender interval too low
- High resolution frames

**Solutions**:
- Keep `gender_interval = 5` in code
- Ensure frame resizing is working
- Consider GPU acceleration for production

### Inaccurate Classifications

**Causes**:
- Poor lighting
- Side profiles
- Face partially obscured
- Threshold too low

**Solutions**:
- Improve lighting conditions
- Adjust camera angle
- Increase `GENDER_THRESHOLD` to 0.7
- Accept "Unknown" as valid result

## Technical Details

### DeepFace Models

Available detector backends:
- **opencv** (default): Fast, works well across ethnicities
- **ssd**: More accurate, slower
- **mtcnn**: Best for Asian faces, slower
- **retinaface**: High accuracy, slowest

Current: `opencv` for speed/accuracy balance

### Model Files

DeepFace automatically downloads model weights on first use:
- Location: `~/.deepface/weights/`
- Size: ~100MB total
- Internet required for first run

### API Response

```json
{
  "current": {
    "total_people": 3,
    "male": 1,
    "female": 1,
    "unknown": 1,
    "fps": 14
  },
  "session": {
    "total_detected": 450,
    "male_detected": 180,
    "female_detected": 200
  }
}
```

## Future Improvements

1. **Age Estimation**: Add age range detection
2. **Ethnicity Detection**: Optional ethnicity classification
3. **GPU Acceleration**: 3-5x faster with CUDA
4. **Custom Model**: Train on Malaysian-specific dataset
5. **Emotion Detection**: Facial expression analysis
6. **Database Logging**: Store statistics for analytics

## References

- DeepFace: https://github.com/serengil/deepface
- Face Recognition: https://pypi.org/project/face-recognition/
- Malaysian PDPA: https://www.pdp.gov.my/

---

**Last Updated**: 2026-01-31
**Version**: 1.0
**Status**: Production Ready

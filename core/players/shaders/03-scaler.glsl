//!PARAM scaler_width
//!TYPE float
//!MINIMUM 1.0
//!MAXIMUM 8192.0
256.0

//!PARAM scaler_height
//!TYPE float
//!MINIMUM 1.0
//!MAXIMUM 8192.0
512.0

//!PARAM scaler_sourcealign
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 1.0
1.0

//!PARAM scaler_sourceoffset_x
//!TYPE float
//!MINIMUM -4096.0
//!MAXIMUM 4096.0
0.0

//!PARAM scaler_sourceoffset_y
//!TYPE float
//!MINIMUM -4096.0
//!MAXIMUM 4096.0
0.0

//!PARAM scaler_fit
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 2.0
0.0

//!PARAM scaler_output_x
//!TYPE float
//!MINIMUM -8192.0
//!MAXIMUM 8192.0
0.0

//!PARAM scaler_output_y
//!TYPE float
//!MINIMUM -8192.0
//!MAXIMUM 8192.0
0.0

//!PARAM scaler_halfheight
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 1.0
0.0

//!PARAM scaler_rotate
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 359.0
0.0

//!PARAM scaler_enable
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 1.0
1.0

//!HOOK MAIN
//!BIND HOOKED
//!WIDTH HOOKED.w
//!HEIGHT HOOKED.h
//!DESC Live Video Scaler

/*
    LED Scaler Shader
    Scales and crops video input to fit LED display dimensions.
    Parameters:
        scaler_height                - Target height in pixels
        scaler_width                - Target width in pixels
        scaler_sourcealign      - Crop alignment option [1.0 = center, 0.0 = left]
        scaler_sourceoffset_x   - Horizontal crop/content offset in pixels
        scaler_sourceoffset_y   - Vertical crop/content offset in pixels
        scaler_fit              - 0 = cover (crop the source to the target aspect, default)
                                  1 = contain (whole source inside the target, black bars)
                                  2 = stretch (ignore the source aspect)
        scaler_output_x/y       - Where the finished (rotated, reshaped) block lands on
                                  screen, in output pixels from the top-left [default 0,0]
        scaler_halfheight       - Half-height reshape option for LED display [1.0 = enabled, 0.0 = disabled]
        scaler_rotate           - Rotation in degrees [0.0-359.0]
        scaler_enable           - Enable or disable processing [1.0 = enabled, 0.0 = disabled]
*/

#define PI 3.14159265359

vec4 hook() {
    // Bypass if disabled
    if (scaler_enable < 0.5) {
        return HOOKED_tex(HOOKED_pos);
    }

    // Parameters
    float TARGET_HEIGHT = scaler_height > 0.0 ? scaler_height : HOOKED_size.y;
    float TARGET_WIDTH  = scaler_width > 0.0 ? scaler_width : HOOKED_size.x;
    int CROP_ALIGN_CENTER = int(scaler_sourcealign);
    float CROP_OFFSET_X = scaler_sourceoffset_x;
    float CROP_OFFSET_Y = scaler_sourceoffset_y;
    int FIT = int(scaler_fit + 0.5);
    int HALF_HEIGHT_RESHAPE = int(scaler_halfheight);
    float ROTATE_DEG = scaler_rotate;
    
    // Source dimensions
    vec2 srcSize = HOOKED_size;
    
    // Step 1: Compute crop zone in source that matches target aspect ratio
    float targetAspect = TARGET_WIDTH / TARGET_HEIGHT;
    float srcAspect = srcSize.x / srcSize.y;
    
    vec2 cropSize;
    if (srcAspect > targetAspect) {
        // Source is wider - crop width
        cropSize.y = srcSize.y;
        cropSize.x = srcSize.y * targetAspect;
    } else {
        // Source is taller - crop height
        cropSize.x = srcSize.x;
        cropSize.y = srcSize.x / targetAspect;
    }
    
    // Crop offset (centered or left-aligned + manual offset)
    vec2 cropOffset;
    if (CROP_ALIGN_CENTER == 1) {
        cropOffset.x = (srcSize.x - cropSize.x) / 2.0;
    } else {
        cropOffset.x = 0.0;
    }
    cropOffset.x += CROP_OFFSET_X * (cropSize.x / TARGET_WIDTH); // Scale offset to source space
    cropOffset.y = (srcSize.y - cropSize.y) / 2.0 + CROP_OFFSET_Y * (cropSize.y / TARGET_HEIGHT);
    
    // Clamp crop offset to valid range
    cropOffset.x = clamp(cropOffset.x, 0.0, srcSize.x - cropSize.x);
    cropOffset.y = clamp(cropOffset.y, 0.0, srcSize.y - cropSize.y);
    
    // Step 2: Content size after scaling (before halfheight, which is applied after rotation)
    float contentW = TARGET_WIDTH;
    float contentH = TARGET_HEIGHT;
    
    // Step 3: Rotation setup
    float angleRad = ROTATE_DEG * PI / 180.0;
    float cosA = cos(angleRad);
    float sinA = sin(angleRad);
    
    // Compute rotated bounding box size
    // The 4 corners of content rect relative to center
    vec2 halfContent = vec2(contentW, contentH) / 2.0;
    vec2 corners[4];
    corners[0] = vec2(-halfContent.x, -halfContent.y);
    corners[1] = vec2( halfContent.x, -halfContent.y);
    corners[2] = vec2( halfContent.x,  halfContent.y);
    corners[3] = vec2(-halfContent.x,  halfContent.y);
    
    // Rotate corners and find bounding box
    vec2 minBB = vec2(1e10);
    vec2 maxBB = vec2(-1e10);
    for (int i = 0; i < 4; i++) {
        vec2 rotated;
        rotated.x = corners[i].x * cosA - corners[i].y * sinA;
        rotated.y = corners[i].x * sinA + corners[i].y * cosA;
        minBB = min(minBB, rotated);
        maxBB = max(maxBB, rotated);
    }
    vec2 bbSize = maxBB - minBB;
    
    // Step 4: Apply halfheight to the rotated bounding box
    float finalW = bbSize.x;
    float finalH = HALF_HEIGHT_RESHAPE == 1 ? (bbSize.y / 2.0) : bbSize.y;
    
    // Step 5: Position offset to align rotated content to top-left
    // The rotated bounding box top-left corner should be at (0,0)
    vec2 bbOffset = -minBB; // This moves the BB so its min corner is at origin
    
    // Current output pixel position in canvas, relative to where the block is placed
    vec2 outPixel = HOOKED_pos * target_size - vec2(scaler_output_x, scaler_output_y);
    
    // Check if pixel is within the final output area
    if (outPixel.x < 0.0 || outPixel.y < 0.0 || outPixel.x >= finalW || outPixel.y >= finalH) {
        return vec4(0.0, 0.0, 0.0, 1.0);
    }
    
    // Step 6: Inverse transform - go from output pixel back to content space
    // First, undo halfheight
    vec2 rotatedPos = outPixel;
    if (HALF_HEIGHT_RESHAPE == 1) {
        rotatedPos.y *= 2.0;
    }
    
    // Position relative to rotated content center
    vec2 posInBB = rotatedPos - bbOffset;
    
    // Inverse rotation (rotate by -angle)
    vec2 contentPos;
    contentPos.x = posInBB.x * cosA + posInBB.y * sinA;
    contentPos.y = -posInBB.x * sinA + posInBB.y * cosA;
    
    // Shift from center-relative to top-left-relative
    contentPos += halfContent;
    
    // Check bounds in content space
    if (contentPos.x < 0.0 || contentPos.x >= contentW ||
        contentPos.y < 0.0 || contentPos.y >= contentH) {
        return vec4(0.0, 0.0, 0.0, 1.0);
    }
    
    // Step 7: Map from target space to the source
    vec2 srcPos;
    if (FIT == 1) {
        // contain: the whole source, aspect kept, inside the target — black around it
        vec2 fitSize;
        if (srcAspect > targetAspect) { fitSize.x = TARGET_WIDTH;  fitSize.y = TARGET_WIDTH / srcAspect; }
        else                          { fitSize.y = TARGET_HEIGHT; fitSize.x = TARGET_HEIGHT * srcAspect; }
        vec2 fitOffset = (vec2(TARGET_WIDTH, TARGET_HEIGHT) - fitSize) / 2.0;
        if (CROP_ALIGN_CENTER == 0) fitOffset.x = 0.0;
        fitOffset += vec2(CROP_OFFSET_X, CROP_OFFSET_Y);
        vec2 c = contentPos - fitOffset;
        if (c.x < 0.0 || c.y < 0.0 || c.x >= fitSize.x || c.y >= fitSize.y) {
            return vec4(0.0, 0.0, 0.0, 1.0);
        }
        srcPos = c / fitSize * srcSize;
    } else if (FIT == 2) {
        // stretch: target fully covered, source aspect ignored
        srcPos = contentPos / vec2(TARGET_WIDTH, TARGET_HEIGHT) * srcSize;
    } else {
        // cover (default): the crop zone computed in step 1
        vec2 cropPos = contentPos / vec2(TARGET_WIDTH, TARGET_HEIGHT);
        srcPos = cropOffset + cropPos * cropSize;
    }
    
    // Normalize to texture coordinates
    vec2 texCoord = srcPos / srcSize;
    
    // Final bounds check
    if (texCoord.x < 0.0 || texCoord.x > 1.0 ||
        texCoord.y < 0.0 || texCoord.y > 1.0) {
        return vec4(0.0, 0.0, 0.0, 1.0);
    }
    
    return HOOKED_tex(texCoord);
}
//!PARAM scaler_h
//!TYPE float
//!MINIMUM 1.0
//!MAXIMUM 8192.0
1024.0

//!PARAM scaler_w
//!TYPE float
//!MINIMUM 1.0
//!MAXIMUM 8192.0
512.0

//!PARAM scaler_align
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 1.0
1.0

//!PARAM scaler_offset_x
//!TYPE float
//!MINIMUM -4096.0
//!MAXIMUM 4096.0
0.0

//!PARAM scaler_reshape
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 1.0
1.0

//!PARAM scaler_enable
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 1.0
0.0

//!HOOK MAIN
//!BIND HOOKED
//!WIDTH HOOKED.w
//!HEIGHT HOOKED.h
//!DESC Live Video Scaler

/*
    LED Scaler Shader
    Scales and crops video input to fit LED display dimensions.
    Parameters:
        scaler_h          - Target height in pixels
        scaler_w          - Target width in pixels
        scaler_align      - Crop alignment option [1.0 = center, 0.0 = left]
        scaler_offset_x   - Horizontal crop offset in pixels
        scaler_reshape    - Half-height reshape option for LED display [1.0 = enabled, 0.0 = disabled]
        scaler_enable     - Enable or disable processing [1.0 = enabled, 0.0 = disabled]
*/

vec4 hook() {
    // Map Params to your Logic Variables
    float enable_processing = scaler_enable;

    // Bypass if disabled
    if (enable_processing < 0.5) {
        return HOOKED_tex(HOOKED_pos);
    }

    // Local variable mapping
    float TARGET_HEIGHT = scaler_h > 0.0 ? scaler_h : HOOKED_size.y;
    float TARGET_WIDTH  = scaler_w > 0.0 ? scaler_w : HOOKED_size.x;
    int CROP_ALIGN_CENTER = int(scaler_align);
    float CROP_OFFSET_X = scaler_offset_x;
    int HALF_HEIGHT_RESHAPE = int(scaler_reshape);

    float outputWidth = TARGET_WIDTH;
    float outputHeight = HALF_HEIGHT_RESHAPE == 1 ? (TARGET_HEIGHT / 2.0) : TARGET_HEIGHT;
    
    // 'target_size' is provided by mpv context (Output Resolution)
    vec2 outPixel = HOOKED_pos * target_size;
    
    if (outPixel.x >= outputWidth || outPixel.y >= outputHeight) {
        return vec4(0.0, 0.0, 0.0, 1.0);
    }
    
    vec2 videoSize = HOOKED_size;
    float videoAspect = videoSize.x / videoSize.y;
    
    float resizedHeight = TARGET_HEIGHT;
    float resizedWidth = resizedHeight * videoAspect;
    
    float verticalScale = HALF_HEIGHT_RESHAPE == 1 ? 2.0 : 1.0;
    vec2 processingPos = outPixel * vec2(1.0, verticalScale);
    
    float cropOffsetX = 0.0;
    if (resizedWidth > TARGET_WIDTH) {
        if (CROP_ALIGN_CENTER == 1) {
            cropOffsetX = (resizedWidth - TARGET_WIDTH) / 2.0;
        } else {
            cropOffsetX = 0.0;
        }
    } else {
        if (CROP_ALIGN_CENTER == 1) {
            cropOffsetX = -(TARGET_WIDTH - resizedWidth) / 2.0;
        } else {
            cropOffsetX = 0.0;
        }
    }
    
    cropOffsetX += CROP_OFFSET_X;
    processingPos.x += cropOffsetX;
    
    if (processingPos.x < 0.0 || processingPos.x >= resizedWidth ||
        processingPos.y < 0.0 || processingPos.y >= resizedHeight) {
        return vec4(0.0, 0.0, 0.0, 1.0);
    }
    
    vec2 videoPos = processingPos / vec2(resizedWidth, resizedHeight);
    return HOOKED_tex(videoPos);
}
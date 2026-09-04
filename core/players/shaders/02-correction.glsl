//!PARAM correction_brightness
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 200.0
100.0

//!PARAM correction_contrast
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 300.0
100.0

//!PARAM correction_saturation
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 300.0
100.0

//!PARAM correction_gamma
//!TYPE float
//!MINIMUM 0.1
//!MAXIMUM 5.0
1.0

//!PARAM correction_temp
//!TYPE float
//!MINIMUM -100.0
//!MAXIMUM 100.0
0.0

//!PARAM correction_tint
//!TYPE float
//!MINIMUM -100.0
//!MAXIMUM 100.0
0.0

//!PARAM correction_hue
//!TYPE float
//!MINIMUM -180.0
//!MAXIMUM 180.0
0.0

//!PARAM correction_vibrance
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 200.0
100.0

//!PARAM correction_exposure
//!TYPE float
//!MINIMUM -5.0
//!MAXIMUM 5.0
0.0

//!PARAM correction_shadows
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 200.0
100.0

//!PARAM correction_midtones
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 200.0
100.0

//!PARAM correction_highlights
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 200.0
100.0

//!HOOK MAIN
//!BIND HOOKED
//!DESC Color Correction

/*
    Color Correction Shader
    Comprehensive color grading and correction for video output.
    
    Parameters:
        correction_brightness  - Overall brightness (0-200, default 100)
        correction_contrast    - Contrast adjustment (0-300, default 100)
        correction_saturation  - Color saturation (0-300, default 100)
        correction_gamma       - Gamma correction (0.1-5.0, default 1.0)
        correction_temp        - Color temperature, warm/cool (-100 to 100, default 0)
        correction_tint        - Green/magenta tint (-100 to 100, default 0)
        correction_hue         - Hue rotation in degrees (-180 to 180, default 0)
        correction_vibrance    - Smart saturation (0-200, default 100)
        correction_exposure    - Exposure compensation in stops (-5 to 5, default 0)
        correction_shadows     - Shadow adjustment (0-200, default 100)
        correction_midtones    - Midtone adjustment (0-200, default 100)
        correction_highlights  - Highlight adjustment (0-200, default 100)
*/

// RGB to luminance weights (ITU-R BT.709)
const vec3 LUMA_WEIGHTS = vec3(0.2126, 0.7152, 0.0722);

// Convert RGB to HSV
vec3 rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

// Convert HSV to RGB
vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

// Tone curve for selective color adjustments
float toneCurve(float x, float shadows, float midtones, float highlights) {
    // Use smooth curves to target different tonal ranges
    float s = shadows * smoothstep(0.0, 0.3, 1.0 - x);
    float m = midtones * (1.0 - smoothstep(0.3, 0.7, abs(x - 0.5) * 2.0));
    float h = highlights * smoothstep(0.7, 1.0, x);
    return s + m + h;
}

vec4 hook() {
    vec4 color = HOOKED_tex(HOOKED_pos);
    vec3 rgb = color.rgb;
    
    // === EXPOSURE ===
    if (abs(correction_exposure) > 0.001) {
        rgb *= pow(2.0, correction_exposure);
    }
    
    // === BRIGHTNESS ===
    float brightness = (correction_brightness - 100.0) / 100.0;
    if (abs(brightness) > 0.001) {
        rgb += brightness;
    }
    
    // === CONTRAST ===
    float contrast = correction_contrast / 100.0;
    if (abs(contrast - 1.0) > 0.001) {
        rgb = (rgb - 0.5) * contrast + 0.5;
    }
    
    // === SELECTIVE TONE ADJUSTMENTS ===
    float shadows = correction_shadows / 100.0;
    float midtones = correction_midtones / 100.0;
    float highlights = correction_highlights / 100.0;
    
    if (abs(shadows - 1.0) > 0.001 || abs(midtones - 1.0) > 0.001 || abs(highlights - 1.0) > 0.001) {
        float luma = dot(rgb, LUMA_WEIGHTS);
        float adjustment = toneCurve(luma, shadows - 1.0, midtones - 1.0, highlights - 1.0);
        rgb += adjustment * 0.2;
    }
    
    // === WHITE BALANCE (Temperature & Tint) ===
    if (abs(correction_temp) > 0.1 || abs(correction_tint) > 0.1) {
        float temp = correction_temp / 100.0;
        float tint = correction_tint / 100.0;
        
        // Temperature: shift red-blue axis
        rgb.r += temp * 0.3;
        rgb.b -= temp * 0.3;
        
        // Tint: shift green-magenta axis
        rgb.g += tint * 0.3;
    }
    
    // === SATURATION ===
    float saturation = correction_saturation / 100.0;
    if (abs(saturation - 1.0) > 0.001) {
        float luma = dot(rgb, LUMA_WEIGHTS);
        rgb = mix(vec3(luma), rgb, saturation);
    }
    
    // === VIBRANCE (smart saturation) ===
    float vibrance = correction_vibrance / 100.0;
    if (abs(vibrance - 1.0) > 0.001) {
        float luma = dot(rgb, LUMA_WEIGHTS);
        float mask = 1.0 - abs(saturation - 1.0); // Affect less saturated colors more
        vec3 vibranceAdjust = mix(vec3(luma), rgb, vibrance);
        rgb = mix(rgb, vibranceAdjust, mask);
    }
    
    // === HUE ROTATION ===
    if (abs(correction_hue) > 0.1) {
        vec3 hsv = rgb2hsv(rgb);
        hsv.x += correction_hue / 360.0;
        hsv.x = fract(hsv.x); // Wrap around
        rgb = hsv2rgb(hsv);
    }
    
    // === GAMMA ===
    if (abs(correction_gamma - 1.0) > 0.001) {
        rgb = pow(max(rgb, vec3(0.0)), vec3(1.0 / correction_gamma));
    }
    
    // Clamp final output
    color.rgb = clamp(rgb, 0.0, 1.0);
    
    return color;
}


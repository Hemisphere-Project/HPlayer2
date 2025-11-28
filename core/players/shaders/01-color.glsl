//!PARAM color_r
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 255.0
0.0

//!PARAM color_g
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 255.0
0.0

//!PARAM color_b
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 255.0
0.0

//!PARAM color_alpha
//!TYPE float
//!MINIMUM 0.0
//!MAXIMUM 255.0
0.0

//!HOOK MAIN
//!BIND HOOKED
//!DESC Live Color Overlay

/*
    Color Overlay Shader
    Applies a solid color overlay to the video input based on RGBA parameters.
    Parameters:
        color_r       - Red component (0-255)
        color_g       - Green component (0-255)
        color_b       - Blue component (0-255)
        color_alpha   - Alpha transparency (0-255)
*/

vec4 hook() {
    vec4 vid = HOOKED_tex(HOOKED_pos);
    
    // Normalize 0-255 to 0.0-1.0
    float a = color_alpha / 255.0;
    
    // Bypass optimization
    if (a <= 0.001) {
        return vid;
    }

    vec3 tint = vec3(color_r, color_g, color_b) / 255.0;
    
    // Mix solid color based on alpha
    vid.rgb = mix(vid.rgb, tint, a);
    
    return vid;
}
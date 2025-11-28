import subprocess
import socket
import json
import time
import math
import os
import sys

#Paths
SOCKET_PATH = "/tmp/mpv_socket"
SHADER_COLOR = os.path.abspath("01-color.glsl")
SHADER_SCALER = os.path.abspath("02-scaler.glsl")
VIDEO_PATH = "/data/usb/mountain-4k.mp4"  # Change to your test video path

# Global State Dictionary
# Initialize with your desired defaults
shader_state = {
    # Color Shader Params
    "color_r": 255.0,
    "color_g": 255.0,
    "color_b": 255.0,
    "color_alpha": 0.0, # Start disabled
    
    # Scaler Shader Params
    "led_w": 512.0,
    "led_h": 1024.0,
    "led_align": 1.0,
    "led_enable": 1.0, # Enable scaler logic
    "led_reshape": 1.0,
    "led_offset_x": 0.0
}

def send_ipc(sock, cmd):
    """Send raw command dict"""
    try:
        msg = json.dumps(cmd) + "\n"
        sock.sendall(msg.encode('utf-8'))
        sock.settimeout(0.01)
        sock.recv(4096)
    except Exception:
        pass

def update_shaders(sock):
    """Converts the state dict to a comma-separated string and sends it."""
    # Format: key1=val1,key2=val2
    opts_string = ",".join([f"{k}={v:.4f}" for k, v in shader_state.items()])
    
    cmd = {
        "command": ["set_property", "glsl-shader-opts", opts_string]
    }
    send_ipc(sock, cmd)

def main():
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    print("Launching MPV...")
    cmd = [
        "mpv", "--idle", "--keep-open", "--force-window",
        f"--input-ipc-server={SOCKET_PATH}",
        "--vo=gpu-next",
        # Load both shaders at startup
        f"--glsl-shaders={SHADER_COLOR}:{SHADER_SCALER}" 
    ]
    print(" ".join(cmd))
    mpv = subprocess.Popen(cmd)

    # Wait for socket
    while not os.path.exists(SOCKET_PATH):
        time.sleep(0.1)

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCKET_PATH)

    # Load Video
    send_ipc(client, {"command": ["loadfile", VIDEO_PATH]})
    
    print("Running animation loop... (Ctrl+C to stop)")
    start_time = time.time()

    try:
        while mpv.poll() is None:
            t = time.time() - start_time
            
            # --- ANIMATION LOGIC ---
            
            # 1. Color: Cycle Red channel and pulse Alpha
            shader_state["color_r"] = (math.sin(t * 2.0) + 1.0) * 127.5 # 0-255
            shader_state["color_alpha"] = 150.0 # Fixed semi-transparency
            
            # 2. Scaler: Breathe Width
            # Oscillate width between 400 and 600
            shader_state["led_w"] = 500.0 + math.sin(t) * 100.0
            
            # 3. Scaler: Pan Offset
            # Pan left/right
            shader_state["led_offset_x"] = math.cos(t * 0.5) * 50.0

            # --- APPLY UPDATES ---
            update_shaders(client)
            
            time.sleep(0.016) # 60 FPS

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        client.close()
        mpv.terminate()
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)

if __name__ == "__main__":
    main()
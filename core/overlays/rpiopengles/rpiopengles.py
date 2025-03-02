import ctypes
import time
import math

# Pick up our constants extracted from the header files with prepare_constants.py
from .egl import *
from .gl2 import *
from .gl2ext import *

# Define verbose=True to get debug messages
verbose = True

# Define some extra constants that the automatic extraction misses
EGL_DEFAULT_DISPLAY = 0
EGL_NO_CONTEXT = 0
EGL_NO_DISPLAY = 0
EGL_NO_SURFACE = 0
DISPMANX_PROTECTION_NONE = 0

# Open the libraries
# bcm = ctypes.CDLL('libbcm_host.so')
drm = ctypes.CDLL('libdrm.so')
gbm = ctypes.CDLL('libgbm.so')
opengles = ctypes.CDLL('libGLESv2.so')
openegl = ctypes.CDLL('libEGL.so')

eglint = ctypes.c_int
eglshort = ctypes.c_short
eglfloat = ctypes.c_float

def eglints(L):
    """Converts a tuple to an array of eglints (would a pointer return be better?)"""
    return (eglint*len(L))(*L)

def eglfloats(L):
    return (eglfloat*len(L))(*L)

def check(e):
    """Checks that error is zero"""
    if e==0: return
    if verbose:
        print ('Error code',hex(e&0xffffffff))
    raise ValueError

class EGL(object):
    
    def __init__(self, depthbuffer=False):
        self.display = openegl.eglGetDisplay(EGL_DEFAULT_DISPLAY)
        if not self.display:
            raise RuntimeError("Failed to get EGL display")

        major = ctypes.c_int()
        minor = ctypes.c_int()
        r = openegl.eglInitialize(self.display, ctypes.byref(major), ctypes.byref(minor))
        if not r:
            raise RuntimeError("Failed to initialize EGL")
        
        print(f"EGL version: {major.value}.{minor.value}")

        # EGL configuration
        config_attribs = eglints((
            EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
            EGL_RED_SIZE, 8,
            EGL_GREEN_SIZE, 8,
            EGL_BLUE_SIZE, 8,
            EGL_ALPHA_SIZE, 8,
            EGL_DEPTH_SIZE, 16 if depthbuffer else 0,
            EGL_NONE
        ))

        num_configs = ctypes.c_int()
        config = ctypes.c_void_p()
        r = openegl.eglChooseConfig(self.display, config_attribs, ctypes.byref(config), 1, ctypes.byref(num_configs))
        if not r or num_configs.value == 0:
            raise RuntimeError("Failed to choose EGL config")

        r = openegl.eglBindAPI(EGL_OPENGL_ES_API)
        if not r:
            raise RuntimeError("Failed to bind OpenGL ES API")

        context_attribs = eglints((EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE))
        self.context = openegl.eglCreateContext(self.display, config, EGL_NO_CONTEXT, context_attribs)
        if self.context == EGL_NO_CONTEXT:
            raise RuntimeError("Failed to create EGL context")

        # DRM and GBM setup
        self.fd = drm.open(b"/dev/dri/card0", os.O_RDWR)
        if self.fd < 0:
            raise RuntimeError("Failed to open DRM device")

        self.gbm_device = gbm.gbm_create_device(self.fd)
        if not self.gbm_device:
            raise RuntimeError("Failed to create GBM device")

        self.width = 800  # Set your desired width
        self.height = 600  # Set your desired height

        self.gbm_surface = gbm.gbm_surface_create(self.gbm_device, self.width, self.height, GBM_FORMAT_XRGB8888, GBM_BO_USE_RENDERING | GBM_BO_USE_SCANOUT)
        if not self.gbm_surface:
            raise RuntimeError("Failed to create GBM surface")

        self.surface = openegl.eglCreateWindowSurface(self.display, config, self.gbm_surface, None)
        if self.surface == EGL_NO_SURFACE:
            raise RuntimeError("Failed to create EGL surface")

        r = openegl.eglMakeCurrent(self.display, self.surface, self.surface, self.context)
        if not r:
            raise RuntimeError("Failed to make EGL context current")

        print("EGL initialization successful")

    # def __init__(self,depthbuffer=False):
    #     """Opens up the OpenGL library and prepares a window for display"""
    #     b = bcm.bcm_host_init()
    #     assert b==0
    #     self.display = openegl.eglGetDisplay(EGL_DEFAULT_DISPLAY)
    #     assert self.display
    #     r = openegl.eglInitialize(self.display,0,0)
    #     assert r
    #     if depthbuffer:
    #         attribute_list = eglints(     (EGL_RED_SIZE, 8,
    #                                   EGL_GREEN_SIZE, 8,
    #                                   EGL_BLUE_SIZE, 8,
    #                                   EGL_ALPHA_SIZE, 8,
    #                                   EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
    #                                   EGL_DEPTH_SIZE, 16,
    #                                   EGL_NONE) )
    #     else:
    #         attribute_list = eglints(     (EGL_RED_SIZE, 8,
    #                                   EGL_GREEN_SIZE, 8,
    #                                   EGL_BLUE_SIZE, 8,
    #                                   EGL_ALPHA_SIZE, 8,
    #                                   EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
    #                                   EGL_NONE) )
    #     # EGL_SAMPLE_BUFFERS,  1,
    #     # EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,

    #     numconfig = eglint()
    #     config = ctypes.c_void_p()
    #     r = openegl.eglChooseConfig(self.display,
    #                                  ctypes.byref(attribute_list),
    #                                  ctypes.byref(config), 1,
    #                                  ctypes.byref(numconfig));
    #     assert r
    #     r = openegl.eglBindAPI(EGL_OPENGL_ES_API)
    #     assert r
    #     # if verbose:
    #     #     print ('numconfig=',numconfig)
    #     context_attribs = eglints( (EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE) )
    #     self.context = openegl.eglCreateContext(self.display, config,
    #                                     EGL_NO_CONTEXT,
    #                                     ctypes.byref(context_attribs))
    #     assert self.context != EGL_NO_CONTEXT
    #     width = eglint()
    #     height = eglint()
    #     s = bcm.graphics_get_display_size(0,ctypes.byref(width),ctypes.byref(height))
    #     self.width = width
    #     self.height = height
    #     assert s>=0
    #     dispman_display = bcm.vc_dispmanx_display_open(0)
    #     dispman_update = bcm.vc_dispmanx_update_start( 0 )
    #     dst_rect = eglints( (0,0,width.value,height.value) )
    #     src_rect = eglints( (0,0,width.value<<16, height.value<<16) )
    #     assert dispman_update
    #     assert dispman_display
    #     dispman_element = bcm.vc_dispmanx_element_add ( dispman_update, dispman_display,
    #                               0, ctypes.byref(dst_rect), 0,
    #                               ctypes.byref(src_rect),
    #                               DISPMANX_PROTECTION_NONE,
    #                               0 , 0, 0)
    #     bcm.vc_dispmanx_update_submit_sync( dispman_update )
    #     nativewindow = eglints((dispman_element,width,height));
    #     nw_p = ctypes.pointer(nativewindow)
    #     self.nw_p = nw_p
    #     self.surface = openegl.eglCreateWindowSurface( self.display, config, nw_p, 0)
    #     assert self.surface != EGL_NO_SURFACE
    #     r = openegl.eglMakeCurrent(self.display, self.surface, self.surface, self.context)
    #     assert r

class colortexture():

    def __init__(self):
        self.egl = EGL()
        
    def draw(self, red=0.0, green=0.0, blue=0.0, alpha=0.0):
        opengles.glBindFramebuffer(GL_FRAMEBUFFER, 0)
        opengles.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        opengles.glClearColor(eglfloat(red), eglfloat(green), eglfloat(blue), eglfloat(alpha))
        self.check()

        openegl.eglSwapBuffers(self.egl.display, self.egl.surface)
        bo = gbm.gbm_surface_lock_front_buffer(self.egl.gbm_surface)
        drm.drmModeSetCrtc(self.egl.fd, self.egl.crtc_id, gbm.gbm_bo_get_handle(bo).u32, 0, 0, self.egl.connector_id, 1, self.egl.mode)
        gbm.gbm_surface_release_buffer(self.egl.gbm_surface, bo)
        self.check()

    # def draw(self, red=0.0, green=0.0, blue=0.0, alpha=0.0):

    #     # Now render to the main frame buffer
    #     opengles.glBindFramebuffer(GL_FRAMEBUFFER,0)

    #     # Clear the background (not really necessary I suppose)
    #     opengles.glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    #     opengles.glClearColor ( eglfloat(red), eglfloat(green), eglfloat(blue), eglfloat(alpha) );
    #     self.check()

    #     openegl.eglSwapBuffers(self.egl.display, self.egl.surface);
    #     self.check()

    def check(self):
        e=opengles.glGetError()
        if e:
            print (hex(e))
            raise ValueError

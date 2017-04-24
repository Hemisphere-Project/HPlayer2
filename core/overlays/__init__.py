import importlib


def getOverlay(name):
    module = importlib.import_module("overlays."+name)
    return getattr(module, name.title()+"Overlay")

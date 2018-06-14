import importlib


def getInterface(name):
    module = importlib.import_module("core.interfaces."+name)
    return getattr(module, name.title()+"Interface")

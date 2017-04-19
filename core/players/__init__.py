import importlib


def getPlayer(name):
    module = importlib.import_module("players."+name)
    return getattr(module, name.title()+"Player")
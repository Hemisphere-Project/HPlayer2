
def getPlayer(name):
    from importlib import import_module
    module = import_module("core.players."+name)
    return getattr(module, name.title()+"Player")

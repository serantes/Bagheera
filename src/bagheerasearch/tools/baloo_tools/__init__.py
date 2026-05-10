from .baloo_tools import BalooTools


def get_info(id):
    """Interfaz simplificada para la librería."""
    tools = BalooTools()
    return tools.get_info(id)


def get_resolution(id):
    """Interfaz simplificada para la librería."""
    tools = BalooTools()
    return tools.get_resolution(id)


def get_tags(id):
    """Interfaz simplificada para la librería."""
    tools = BalooTools()
    return tools.get_tags(id)

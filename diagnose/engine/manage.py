import importlib
from dataclasses import dataclass, field
from typing import Optional, ClassVar, Dict, Type, Sequence

from diagnose.logs import Logger
from diagnose.typings import TPlugin


@dataclass
class PluginDescriptor:
    enable: bool = field(default=False)
    plugin: TPlugin = field(default=None)

    def __repr__(self):
        return f'<PluginDescriptor enable={self.enable}> plugin={self.plugin.__name__}>'


class PluginManager:
    plugins: ClassVar[Dict[str, PluginDescriptor]] = dict()

    @classmethod
    def add_plugin(cls, enabled: bool = False, *args, **kwargs):
        def _inner(plugin_cls: Type['TPlugin']):
            if plugin_cls.__name__ in cls.plugins.keys():
                raise RuntimeError(f"The plugin {plugin_cls.__name__} is duplicated")
            plugin = plugin_cls(*args, **kwargs)
            cls.plugins[plugin_cls.__name__] = PluginDescriptor(enable=enabled, plugin=plugin)

        return _inner

    @classmethod
    def load_plugins(cls, plugin_names: Sequence[str]):
        for plugin_name in plugin_names:
            try:
                importlib.import_module(plugin_name)
            except ModuleNotFoundError:
                Logger.get_logger('engine').error(f"Cannot find plugin {plugin_name}", exc_info=True)

    @classmethod
    def enable_plugin(cls, plugin_cls_name: str) -> None:
        for plugin_name, plugin_disc in cls.plugins.items():
            if plugin_name == plugin_cls_name:
                cls.plugins[plugin_name].enable = True
                return
        Logger.get_logger('engine').warning(f"Cannot find target plugin {plugin_cls_name}")

    @classmethod
    def get_plugin(cls, plugin_cls_name: str) -> Optional['TPlugin']:
        for plugin_name, plugin_disc in cls.plugins.items():
            if plugin_name == plugin_cls_name:
                return plugin_disc.plugin
        Logger.get_logger('engine').warning(f"Cannot find target plugin {plugin_cls_name}")
        return None

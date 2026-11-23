"""Shim minimo que sustituye las dos importaciones externas de custom_tools.py (INSTRUCCIONES §5.1).

Original:
    from crewai.tools import BaseTool
    from ..config.config import APP_CONFIG, WORKING_DIR
Replica:
    from microagent_shim import BaseTool
    from microagent_shim import APP_CONFIG, WORKING_DIR

No contiene logica de herramientas. Ver DECISIONES.md (Fase 2).
"""
import os
from typing import Type

from pydantic import BaseModel, ConfigDict


class BaseTool(BaseModel):
    """Sustituto de crewai.tools.BaseTool: solo los campos que usan las clases de custom_tools.py.

    Los atributos que empiezan por guion bajo (`_model`, `_class_info`, `_inverted_deps`, etc.) son atributos
    privados de pydantic, igual que en la clase original de CrewAI, que tambien es un BaseModel de pydantic.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    args_schema: Type[BaseModel]

    def _run(self, *args, **kwargs) -> str:
        raise NotImplementedError

    def run(self, *args, **kwargs) -> str:
        return self._run(*args, **kwargs)


# Original (config/config.py): WORKING_DIR = os.getcwd(), con el proceso lanzado desde la carpeta `microagent/`,
# que contiene context/, database/, resources/ y output/. En la replica esa carpeta es replica-claude-code/.
# No se usa os.getcwd() porque `claude -p` lanza el servidor MCP desde un directorio vacio (_sandbox/).
WORKING_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Original: {"app_name": "jpetstore-6", "model_name": <modelo>, "java_paths": ["src/main/java"]}.
# En la replica "model_name" lleva el identificador de la corrida (§5.1.3): las rutas quedan en
# output/<app>/<run_id>/domains/...
APP_CONFIG = {
    "app_name": os.environ["APP_NAME"],
    "model_name": os.environ["RUN_ID"],
    "java_paths": ["src/main/java"],
}

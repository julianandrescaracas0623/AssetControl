"""Módulo Actividad de la consola de plataforma (spec 017, T6; plan.md §2.1).

``routes`` expone ``GET /plataforma/actividad`` (solo lectura) y ``service`` valida la
consulta y llama a ``acceso.plataforma_listar_auditoria`` de ``app.db``. El registro está en
``app.plataforma.modulos``.
"""

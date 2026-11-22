"""Módulo Usuarios de la consola de plataforma (spec 017, T5; plan.md §2.1).

``routes`` expone ``/plataforma/empresas/{id}/usuarios`` y ``service`` valida y llama a las
funciones ``acceso.plataforma_*`` de ``app.db``. El registro está en
``app.plataforma.modulos``. Sin invitaciones ni altas de usuarios (spec 017, §8 de alcance).
"""

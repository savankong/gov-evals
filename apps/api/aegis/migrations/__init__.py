"""Schema migrations.

This package lives inside `aegis` rather than beside it so that the image
carries it: the Dockerfile copies `apps/api/aegis`, and a migration directory
outside that tree would be absent in production -- which is the same class of
mistake that shipped an image with no evaluation packs in it.
"""

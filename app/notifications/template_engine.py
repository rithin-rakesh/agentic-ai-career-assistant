import os
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from app.config import settings
from app.logger import logger

class TemplateEngine:
    """
    Jinja2 Template render engine.
    Locates and compiles HTML email design templates from app/templates/.
    """
    def __init__(self, template_dir: Optional[str] = None):
        if template_dir is None:
            # Resolve relative app/templates/ path to absolute location
            template_dir = os.path.join(settings.BASE_DIR, "app", "templates")
            
        logger.debug(f"TemplateEngine: Initializing. Directory path: {template_dir}")
        os.makedirs(template_dir, exist_ok=True)
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def render(self, template_name: str, context: dict) -> str:
        """
        Renders an HTML template layout populated with context dictionary parameters.
        """
        try:
            logger.debug(f"TemplateEngine: Rendering template '{template_name}'")
            template = self.env.get_template(template_name)
            rendered_html = template.render(context)
            return rendered_html
        except Exception as e:
            logger.error(f"TemplateEngine: Failed to render template '{template_name}': {e}", exc_info=True)
            raise

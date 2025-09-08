# -*- coding: utf-8 -*-
import os
import sys
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('../'))

html_show_sourcelink = False

# -- General configuration ------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.doctest',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.mathjax',      # ✅ usar MathJax
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinxcontrib.bibtex',
    # 'myst_parser',            # ← opcional si vas a escribir en .md
]
# ❌ quitamos imgmath (era la causa de fórmulas como imágenes)
# ❌ y su opción asociada:
# imgmath_font_size = 12

bibtex_bibfiles = ['references.bib']
bibtex_encoding = 'latin'

napoleon_google_docstring = False
napoleon_use_param = False
napoleon_use_ivar = True

templates_path = ['_templates']
# source_suffix = ['.rst', '.md']   # <- descomenta si usas MyST
source_suffix = '.rst'

master_doc = 'index'

project = u'RADIO'
copyright = u'2025, Guido Godínez Zamora'
author = u'Guido Godínez Zamora'
version = u'Guido Godínez Zamora'
release = u'1.0.a'
language = 'es'

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
pygments_style = 'sphinx'
todo_include_todos = True

# -- MathJax: numeración, macros y cortes automáticos ---------------------
math_number_all = True
math_eqref_format = "({number})"
mathjax3_config = {
    "tex": {
        "tags": "ams",                           # permite \label/\eqref
        "inlineMath": [["\\(", "\\)"], ["$", "$"]],
        "displayMath": [["$$", "$$"], ["\\[", "\\]"]],
        "macros": {
            "DiscountRate": r"\mathrm{DiscountRate}",
            "TotalCost": r"\mathrm{TotalCost}",
            "TotalStorageCost": r"\mathrm{TotalStorageCost}",
            "SalvageValue": r"\mathrm{SalvageValue}",
            # añade más macros que repitas a menudo…
        },
    },
    "chtml": {                                   # saltos automáticos según ancho
        "linebreaks": {"automatic": True, "width": "container"},
        "scale": 0.95,                           # opcional: reduce un 5%
    },
    "svg": {                                     # por si la salida cambiara a SVG
        "linebreaks": {"automatic": True, "width": "container"}
    },
}

# -- HTML output ----------------------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_sidebars = {
    '**': ['relations.html', 'searchbox.html']
}

# Activa estáticos y CSS para fórmulas anchas / columna más amplia (opcional)
#html_static_path = ['_static']
#html_css_files = ['math.css']   # crea docs/_static/math.css

# -- HTMLHelp / LaTeX / man / texinfo ------------------------------------
htmlhelp_basename = 'Documentación'

latex_elements = {}
latex_documents = [
    (master_doc, 'eperdoc.tex', u'Documentation', u'Guido Godínez Zamora')
]

man_pages = [
    (master_doc, 'Documentación', u'Documentación', [author], 1)
]

texinfo_documents = [
    (master_doc, 'Documentación', u'Documentaciónn',
     author, 'Documentación', 'One line description of project.', 'Miscellaneous'),
]

# -- Intersphinx ----------------------------------------------------------
intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}
Ahora crea el archivo docs/_static/math.css (ajústalo a tu gusto):

css
Copy code
/* scroll horizontal si aún queda muy larga */
div.math, .math, mjx-container[display="true"] {
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
  padding-bottom: 0.25rem;
}

/* opcional: ensancha la columna central del tema RTD */
.wy-nav-content { max-width: 1100px; }  /* prueba 1000–1200px */
}

#def setup(app):
    #app.add_css_file('theme_overrides.css')  
# requiere docs/_static/theme_overrides.css

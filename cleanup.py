import re, os

BASE = r'c:\Users\paras\ASTRO\Oil_spill'


def clean_js(content):
    content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
    content = re.sub(r'/\*[\s\S]*?\*/', '', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r'[ \t]+\n', '\n', content)
    return content.strip() + '\n'


def clean_css(content):
    content = re.sub(r'/\*[\s\S]*?\*/', '', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r'[ \t]+\n', '\n', content)
    return content.strip() + '\n'


def clean_html(content):
    content = re.sub(r'<!--[\s\S]*?-->', '', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r'[ \t]+\n', '\n', content)
    return content.strip() + '\n'


files = [
    (r'frontend\script.js',          clean_js),
    (r'frontend\style.css',          clean_css),
    (r'frontend\index.html',         clean_html),
    (r'frontend\command-center.html',clean_html),
    (r'frontend\evidence.html',      clean_html),
    (r'frontend\methodology.html',   clean_html),
    (r'backend\src\app.js',                                    clean_js),
    (r'backend\src\server.js',                                 clean_js),
    (r'backend\src\config\supabase.js',                        clean_js),
    (r'backend\src\controllers\investigations.controller.js',  clean_js),
    (r'backend\src\services\aiClient.js',                      clean_js),
    (r'backend\src\services\dossier.js',                       clean_js),
    (r'backend\src\routes\investigations.routes.js',           clean_js),
]

for rel, fn in files:
    path = os.path.join(BASE, rel)
    if not os.path.exists(path):
        print(f'SKIP (not found): {rel}')
        continue
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()
    cleaned = fn(original)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(cleaned)
    saved = len(original) - len(cleaned)
    print(f'Cleaned {rel}  ({saved:+d} bytes)')

print('\nAll done.')

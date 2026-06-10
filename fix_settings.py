"""Fix settings panel: add providers, key masking, auto re-analyze."""
import sys

PATH = r'D:\全场基金监测\templates\index.html'

with open(PATH, 'r', encoding='utf-8') as f:
    html = f.read()

if len(html) < 1000:
    print('ERROR: HTML file too small, aborting')
    sys.exit(1)

original_len = len(html)

# 1. Add 3 more providers
old_providers = '            <option value="custom">自定义</option>'
new_providers = '''            <option value="deepseek">DeepSeek</option>
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
            <option value="qwen">通义千问</option>
            <option value="ollama">Ollama</option>
            <option value="custom">自定义</option>'''

# The old dropdown has deepseek+openai+custom. Replace the whole select content.
old_select = '<option value="deepseek">DeepSeek</option>\n            <option value="openai">OpenAI</option>\n            <option value="custom">自定义</option>'
new_select = '<option value="deepseek">DeepSeek</option>\n            <option value="openai">OpenAI</option>\n            <option value="anthropic">Anthropic</option>\n            <option value="qwen">通义千问</option>\n            <option value="ollama">Ollama</option>\n            <option value="custom">自定义</option>'

if old_select in html:
    html = html.replace(old_select, new_select)
    print('Providers: updated')
else:
    print('WARNING: old select not found, trying alternative...')
    # Try to find just 'openai' option and insert after it
    alt_old = '<option value="openai">OpenAI</option>'
    alt_new = '<option value="openai">OpenAI</option>\n            <option value="anthropic">Anthropic</option>\n            <option value="qwen">通义千问</option>\n            <option value="ollama">Ollama</option>'
    if alt_old in html:
        html = html.replace(alt_old, alt_new)
        print('Providers: updated (alt method)')
    else:
        print('ERROR: cannot find provider options')

# 2. Update onProviderChange for all providers
old_fn = 'if (p === "openai") { document.getElementById("aiBase").value = "https://api.openai.com/v1"; document.getElementById("aiModel").value = "gpt-4o-mini"; }\n}'
new_fn = '''if (p === "openai") { document.getElementById("aiBase").value = "https://api.openai.com/v1"; document.getElementById("aiModel").value = "gpt-4o-mini"; }
  if (p === "anthropic") { document.getElementById("aiBase").value = "https://api.anthropic.com/v1"; document.getElementById("aiModel").value = "claude-haiku-4-5"; }
  if (p === "qwen") { document.getElementById("aiBase").value = "https://dashscope.aliyuncs.com/compatible-mode/v1"; document.getElementById("aiModel").value = "qwen-turbo"; }
  if (p === "ollama") { document.getElementById("aiBase").value = "http://localhost:11434/v1"; document.getElementById("aiModel").value = "llama3"; }
}'''
if old_fn in html:
    html = html.replace(old_fn, new_fn)
    print('Presets: updated')
else:
    print('WARNING: old presets not found')

# 3. Key masking in load
old_key_load = 'document.getElementById("aiKey").value = ai.key || "";'
new_key_load = '''var k = ai.key || "";
  var masked = k;
  if (k.length > 11) { masked = k.substring(0,3) + "****" + k.substring(k.length-4); }
  document.getElementById("aiKey").value = masked;
  document.getElementById("aiKey").setAttribute("data-full", k);'''
if old_key_load in html:
    html = html.replace(old_key_load, new_key_load)
    print('Key masking: updated')
else:
    print('WARNING: old key load not found')

# 4. Enhanced toggleKeyVisibility
old_toggle = 'function toggleKeyVisibility() { var el = document.getElementById("aiKey"); el.type = el.type === "password" ? "text" : "password"; }'
new_toggle = '''function toggleKeyVisibility() {
  var el = document.getElementById("aiKey");
  if (el.type === "password") {
    el.type = "text";
    el.value = el.getAttribute("data-full") || el.value;
    event.target.textContent = "隐藏";
  } else {
    el.type = "password";
    var full = el.value;
    el.setAttribute("data-full", full);
    if (full.length > 11) { el.value = full.substring(0,3) + "****" + full.substring(full.length-4); }
    event.target.textContent = "显示";
  }
}'''
if old_toggle in html:
    html = html.replace(old_toggle, new_toggle)
    print('Toggle: updated')
else:
    print('WARNING: old toggle not found')

# 5. Auto re-analyze on save
old_saved = 's.style.display = "block";'
new_saved = 's.style.display = "block"; if (agentCode) runAgent();'
if old_saved in html:
    html = html.replace(old_saved, new_saved)
    print('Auto re-analyze: updated')
else:
    print('WARNING: old saved line not found')

if len(html) < original_len - 100:
    print('ERROR: HTML got shorter by', original_len - len(html), 'bytes, aborting')
    sys.exit(1)

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print('Done. HTML size:', len(html), 'bytes (was', original_len, ')')

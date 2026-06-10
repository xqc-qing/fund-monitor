"""
Optimize settings panel:
1. Fix duplicate + button
2. Model -> select dropdown
3. Add Chinese explanations
4. Update JS functions for select
"""
import sys

with open(r'D:\全场基金监测\templates\index.html', 'r', encoding='utf-8') as f:
    html = f.read()

orig = len(html)

# 1. Fix duplicate + button (line 216-217)
dup_pattern = '          <button class="btn btn-outline btn-sm" style="font-size:14px;padding:4px 10px" onclick="toggleSettings()" title="API设置">+</button>\n        <button class="btn btn-outline btn-sm" style="font-size:14px;padding:4px 10px" onclick="toggleSettings()" title="API设置">+</button>'
single = '          <button class="btn btn-outline btn-sm" style="font-size:14px;padding:4px 10px" onclick="toggleSettings()" title="设置">+</button>'
html = html.replace(dup_pattern, single)

# 2. Change model input to select dropdown
# Old: <input id="aiModel" style="width:160px" placeholder="deepseek-chat">
old_model = '<div class="form-group"><label>模型</label><input id="aiModel" style="width:160px" placeholder="deepseek-chat"></div>'
new_model = '''<div class="form-group"><label>模型</label>
          <select id="aiModel" style="width:200px">
            <option value="deepseek-chat">deepseek-chat</option>
            <option value="deepseek-reasoner">deepseek-reasoner (R1)</option>
          </select>
        </div>'''
html = html.replace(old_model, new_model)

# 3. Update onProviderChange to set model select
old_onProviderChange = '''function onProviderChange() {
  var p = document.getElementById("aiProvider").value;
  if (p === "deepseek") { document.getElementById("aiBase").value = "https://api.deepseek.com/v1"; document.getElementById("aiModel").value = "deepseek-chat"; }
  if (p === "openai") { document.getElementById("aiBase").value = "https://api.openai.com/v1"; document.getElementById("aiModel").value = "gpt-4o-mini"; }
  if (p === "anthropic") { document.getElementById("aiBase").value = "https://api.anthropic.com/v1"; document.getElementById("aiModel").value = "claude-haiku-4-5"; }
  if (p === "qwen") { document.getElementById("aiBase").value = "https://dashscope.aliyuncs.com/compatible-mode/v1"; document.getElementById("aiModel").value = "qwen-turbo"; }
  if (p === "ollama") { document.getElementById("aiBase").value = "http://localhost:11434/v1"; document.getElementById("aiModel").value = "llama3"; }
}'''

new_onProviderChange = '''function onProviderChange() {
  var p = document.getElementById("aiProvider").value;
  var modelEl = document.getElementById("aiModel");
  var presets = {
    deepseek:    { base: "https://api.deepseek.com/v1", models: ["deepseek-chat","deepseek-reasoner"] },
    openai:      { base: "https://api.openai.com/v1", models: ["gpt-4o-mini","gpt-4o","gpt-4-turbo"] },
    anthropic:   { base: "https://api.anthropic.com/v1", models: ["claude-haiku-4-5","claude-sonnet-4-6","claude-opus-4-7"] },
    qwen:        { base: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen-turbo","qwen-plus","qwen-max"] },
    ollama:      { base: "http://localhost:11434/v1", models: ["llama3","qwen2.5","deepseek-r1"] },
    custom:      { models: [] }
  };
  var cfg = presets[p] || {};
  if (cfg.base) document.getElementById("aiBase").value = cfg.base;
  var models = cfg.models || [];
  if (models.length > 0) {
    modelEl.innerHTML = models.map(function(m){ return '<option value=\"'+m+'\">'+m+'</option>'; }).join("");
  }
}'''

html = html.replace(old_onProviderChange, new_onProviderChange)

# 4. Update loadAllSettings for model select
old_load_model = 'document.getElementById("aiModel").value = ai.model || "deepseek-chat";'
new_load_model = '''var m = ai.model || "deepseek-chat";
  var modelEl = document.getElementById("aiModel");
  var found = false;
  for (var i=0; i<modelEl.options.length; i++) { if (modelEl.options[i].value === m) { modelEl.value = m; found = true; break; } }
  if (!found && m) { modelEl.innerHTML += '<option value=\"'+m+'\">'+m+' (custom)</option>'; modelEl.value = m; }'''
html = html.replace(old_load_model, new_load_model)

# 5. Add help text under API base URL
old_base = '<div class="form-row" style="margin-bottom:12px">\n        <div class="form-group"><label>API 地址</label><input id="aiBase" class="wide" style="width:400px" placeholder="https://api.deepseek.com/v1"></div>'
new_base = '<div class="form-row" style="margin-bottom:12px">\n        <div class="form-group"><label>API 地址 <span style="font-weight:400;color:var(--muted);font-size:10px">(AI服务的网址，选服务商后自动填写)</span></label><input id="aiBase" class="wide" style="width:400px" placeholder="https://api.deepseek.com/v1"></div>'
html = html.replace(old_base, new_base)

# 6. Add help text under Key
old_key = '<div class="form-group"><label>API Key</label><input id="aiKey" class="wide" style="width:400px" type="password" placeholder="sk-...">'
new_key = '<div class="form-group"><label>API Key <span style="font-weight:400;color:var(--muted);font-size:10px">(在服务商网站申请，如 platform.deepseek.com)</span></label><input id="aiKey" class="wide" style="width:400px" type="password" placeholder="sk-...">'
html = html.replace(old_key, new_key)

# 7. Provider label with help
old_prov = '<div class="form-group"><label>服务商</label>'
new_prov = '<div class="form-group"><label>服务商 <span style="font-weight:400;color:var(--muted);font-size:10px">(选择你使用的AI服务)</span></label>'
html = html.replace(old_prov, new_prov)

if len(html) < orig - 500:
    print('ERROR: size decreased too much')
    sys.exit(1)

with open(r'D:\全场基金监测\templates\index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f'OK: {orig} -> {len(html)} bytes')

# 静态JS库说明

本目录包含Web Demo所需的所有JavaScript库的本地副本，避免依赖外部CDN。

## 已下载的文件

### 1. Vue 3 (vue.global.prod.js)
- **版本**: 3.x (最新稳定版)
- **大小**: ~158 KB
- **用途**: 前端框架，用于所有页面的响应式UI
- **来源**: https://unpkg.com/vue@3/dist/vue.global.prod.js

### 2. Marked.js (marked.min.js)
- **版本**: 12.0.0
- **大小**: ~34 KB
- **用途**: Markdown渲染，用于显示报告内容
- **来源**: https://unpkg.com/marked@12.0.0/marked.min.js

### 3. PDF.js (pdf.min.js)
- **版本**: 3.11.174
- **大小**: ~312 KB
- **用途**: PDF文件解析和渲染
- **来源**: https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js

### 4. PDF.js Worker (pdf.worker.min.js) - 需要手动下载
- **版本**: 3.11.174
- **大小**: ~1.7 MB
- **用途**: PDF.js的Web Worker，用于后台处理PDF
- **下载地址**: https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js

## 手动下载 pdf.worker.min.js

由于文件较大，可能需要手动下载。请按以下步骤操作：

### 方法1: 使用浏览器下载
1. 在浏览器中打开: https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js
2. 右键点击页面 → 另存为
3. 保存到当前目录 (`datahub_agentkit/examples/paper_deepresearch/web_demo/static/js/`)
4. 确保文件名为 `pdf.worker.min.js`

### 方法2: 使用PowerShell下载
```powershell
cd datahub_agentkit/examples/paper_deepresearch/web_demo/static/js
Invoke-WebRequest -Uri "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js" -OutFile "pdf.worker.min.js"
```

### 方法3: 使用curl下载
```bash
cd datahub_agentkit/examples/paper_deepresearch/web_demo/static/js
curl -o pdf.worker.min.js https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js
```

### 方法4: 使用wget下载
```bash
cd datahub_agentkit/examples/paper_deepresearch/web_demo/static/js
wget https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js
```

## 验证下载

下载完成后，检查文件是否存在：

```powershell
Get-ChildItem pdf.worker.min.js | Format-Table Name, Length
```

应该看到文件大小约为 1.7 MB (1,700,000+ 字节)。

## 已更新的HTML文件

以下HTML文件已更新为使用本地JS库：

1. ✅ **index.html** - 使用本地 Vue 3 和 PDF.js
2. ✅ **flow.html** - 使用本地 Vue 3 和 Marked.js
3. ✅ **history.html** - 使用本地 Vue 3 和 Marked.js
4. ✅ **task_detail.html** - 使用本地 Vue 3 和 Marked.js

## 注意事项

- Material Icons 字体仍然使用在线CDN (https://fonts.loli.net)，因为字体文件较大且需要多个文件
- 如果需要完全离线，可以考虑下载Material Icons字体文件到本地
- 所有JS库使用的是生产版本（.prod.js 或 .min.js），体积更小，性能更好

## 更新库版本

如需更新库版本，请访问以下网站下载最新版本：

- Vue 3: https://unpkg.com/vue@3/dist/
- Marked.js: https://unpkg.com/marked/
- PDF.js: https://cdnjs.com/libraries/pdf.js

下载后替换对应文件即可。

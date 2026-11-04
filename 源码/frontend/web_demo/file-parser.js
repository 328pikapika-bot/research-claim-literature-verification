/**
 * 前端文件解析服务
 * 支持PDF、TXT、MD文件的解析
 */

class FileParserService {
  constructor() {
    this.parsedFilesKey = 'claim_consistency_parsed_files';
  }

  /**
   * 解析单个文件
   * @param {File} file - 浏览器File对象
   * @returns {Promise<{fileId: string, name: string, type: string, content: string, size: number}>}
   */
  async parseFile(file) {
    const fileType = this._getFileType(file.name);
    const fileId = this._generateFileId();

    let content = '';

    try {
      if (fileType === 'pdf') {
        content = await this._parsePDF(file);
      } else if (fileType === 'txt' || fileType === 'md') {
        content = await this._parseText(file);
      } else {
        throw new Error(`不支持的文件类型: ${fileType}`);
      }

      return {
        fileId,
        name: file.name,
        type: fileType,
        content: content,
        size: file.size,
        parsedAt: new Date().toISOString(),
      };
    } catch (error) {
      console.error(`文件解析失败 ${file.name}:`, error);
      throw error;
    }
  }

  /**
   * 解析PDF文件 - 使用PDF.js
   * @param {File} file
   * @returns {Promise<string>}
   */
  async _parsePDF(file) {
    if (typeof pdfjsLib === 'undefined') {
      throw new Error('PDF.js库未加载');
    }

    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    
    let fullText = '';
    
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      const pageText = textContent.items.map(item => item.str).join(' ');
      fullText += pageText + '\n\n';
    }

    return this._cleanText(fullText);
  }

  /**
   * 解析文本文件
   * @param {File} file
   * @returns {Promise<string>}
   */
  async _parseText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      
      reader.onload = (e) => {
        const content = e.target.result;
        resolve(this._cleanText(content));
      };
      
      reader.onerror = (e) => {
        reject(new Error('文件读取失败'));
      };
      
      reader.readAsText(file, 'UTF-8');
    });
  }

  /**
   * 清理文本内容
   * @param {string} text
   * @returns {string}
   */
  _cleanText(text) {
    if (!text) return '';
    
    return text
      .replace(/\u200b/g, '')
      .replace(/-\n/g, '')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n[ \t]+/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  /**
   * 获取文件类型
   * @param {string} fileName
   * @returns {string}
   */
  _getFileType(fileName) {
    const ext = fileName.split('.').pop().toLowerCase();
    if (ext === 'pdf') return 'pdf';
    if (ext === 'txt') return 'txt';
    if (ext === 'md' || ext === 'markdown') return 'md';
    return ext;
  }

  /**
   * 生成文件ID
   * @returns {string}
   */
  _generateFileId() {
    return `file_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * 保存解析后的文件到后端（优先）或 localStorage（回退）
   * @param {Array} parsedFiles
   * @throws {Error} 当存储失败时抛出错误
   */
  async saveParsedFiles(parsedFiles) {
    // 优先尝试保存到后端
    try {
      const apiBase = ClaimConsistencyConfig.getApiBase();
      const response = await fetch(`${apiBase}/v1/parsed-files/batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Scope': this._getUserScope(),
        },
        body: JSON.stringify({
          files: parsedFiles.map(f => ({
            fileId: f.fileId,
            name: f.name,
            type: f.type,
            content: f.content,
            size: f.size,
            parsedAt: f.parsedAt,
            url: f.url,
          })),
        }),
      });

      if (response.ok) {
        const result = await response.json();
        console.log(`[OK] 文件已保存到后端: ${result.saved}/${result.total}`);

        // 同时保存到 localStorage 作为缓存（只保存元数据）
        try {
          const metadataOnly = parsedFiles.map(f => ({
            fileId: f.fileId,
            name: f.name,
            type: f.type,
            size: f.size,
            parsedAt: f.parsedAt,
            content: '', // 不保存内容到 localStorage
          }));
          localStorage.setItem(this.parsedFilesKey, JSON.stringify(metadataOnly));
        } catch (localErr) {
          console.warn('localStorage 缓存失败（可忽略）:', localErr);
        }

        return;
      } else if (response.status === 503) {
        // 后端服务不可用，直接抛出错误，不回退到 localStorage
        throw new Error('后端存储服务暂时不可用，请稍后重试或联系管理员部署新版本后端服务。');
      } else {
        console.warn('后端保存失败，回退到 localStorage');
      }
    } catch (err) {
      // 如果是我们主动抛出的错误，直接向上传递
      if (err.message.includes('后端存储服务暂时不可用')) {
        throw err;
      }
      console.warn('后端保存失败，回退到 localStorage:', err);
    }

    // 回退到 localStorage（原有逻辑）
    try {
      const filesToStore = parsedFiles.map(f => ({
        ...f,
        content: f.content.length > 10000 ? f.content.substring(0, 10000) + '...[内容已截断]' : f.content,
      }));

      localStorage.setItem(this.parsedFilesKey, JSON.stringify(filesToStore));
    } catch (e) {
      console.error('保存解析文件失败:', e);

      // 尝试保存更少的内容
      try {
        const metadataOnly = parsedFiles.map(f => ({
          fileId: f.fileId,
          name: f.name,
          type: f.type,
          size: f.size,
          parsedAt: f.parsedAt,
          content: f.content ? f.content.substring(0, 1000) : '',
        }));
        localStorage.setItem(this.parsedFilesKey, JSON.stringify(metadataOnly));
        console.warn('已保存文件元数据（内容已大幅截断）');
      } catch (retryError) {
        console.error('保存文件元数据也失败:', retryError);
        // 尝试只保存文件名和基本信息
        try {
          const minimalData = parsedFiles.map(f => ({
            fileId: f.fileId,
            name: f.name,
            type: f.type,
            size: f.size,
          }));
          localStorage.setItem(this.parsedFilesKey, JSON.stringify(minimalData));
          console.warn('已保存最小文件信息（不含内容）');
        } catch (finalError) {
          console.error('无法保存任何文件信息到localStorage:', finalError);
          // 清理可能损坏的数据
          try {
            localStorage.removeItem(this.parsedFilesKey);
          } catch (cleanupError) {
            // 忽略清理错误
          }
          throw new Error('文件内容过大，超出浏览器存储限制。建议上传较小的文件或减少文件数量。');
        }
      }
    }
  }

  /**
   * 从后端（优先）或 localStorage（回退）获取解析后的文件
   * @returns {Promise<Array>}
   */
  async getParsedFiles() {
    // 优先从后端加载
    try {
      const apiBase = ClaimConsistencyConfig.getApiBase();
      const response = await fetch(`${apiBase}/v1/parsed-files?include_content=true`, {
        headers: {
          'X-User-Scope': this._getUserScope(),
        },
      });

      if (response.ok) {
        const result = await response.json();
        console.log(`[OK] 从后端加载了 ${result.total} 个文件`);
        return result.data.map(f => ({
          fileId: f.file_id,
          name: f.name,
          type: f.type,
          content: f.content,
          size: f.size,
          parsedAt: f.parsed_at,
          url: f.url,
        }));
      } else {
        console.warn('后端加载失败，回退到 localStorage');
      }
    } catch (err) {
      console.warn('后端加载失败，回退到 localStorage:', err);
    }

    // 回退到 localStorage
    try {
      const data = localStorage.getItem(this.parsedFilesKey);
      return data ? JSON.parse(data) : [];
    } catch (e) {
      console.error('读取解析文件失败:', e);
      return [];
    }
  }

  /**
   * 清除解析后的文件（后端 + localStorage）
   */
  async clearParsedFiles() {
    // 清除后端数据
    try {
      const apiBase = ClaimConsistencyConfig.getApiBase();
      const response = await fetch(`${apiBase}/v1/parsed-files`, {
        method: 'DELETE',
        headers: {
          'X-User-Scope': this._getUserScope(),
        },
      });
      if (response.ok) {
        console.log('[OK] 后端文件已清除');
      } else {
        console.warn('后端清除失败:', response.statusText);
      }
    } catch (err) {
      console.warn('后端清除失败:', err);
    }

    // 清除 localStorage
    localStorage.removeItem(this.parsedFilesKey);
  }

  /**
   * 获取用户标识（用于数据隔离）
   * @returns {string}
   * @private
   */
  _getUserScope() {
    // 可以从 cookie、sessionStorage 或其他地方获取用户标识
    // 这里使用简单的默认值
    return sessionStorage.getItem('user_scope') || 'default';
  }
}

window.FileParserService = FileParserService;

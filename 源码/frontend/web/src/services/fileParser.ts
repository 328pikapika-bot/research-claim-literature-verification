import mammoth from 'mammoth'
import * as pdfjsLib from 'pdfjs-dist'
import pdfWorkerSrc from 'pdfjs-dist/build/pdf.worker.mjs?url'

import { apiRequest } from './api'
import type { ParsedFileMeta } from '../types'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerSrc

const SUPPORTED_TYPES = new Set(['pdf', 'txt', 'md', 'docx'])

export async function parseFiles(files: File[]): Promise<ParsedFileMeta[]> {
  const results: ParsedFileMeta[] = []
  for (const file of files) {
    results.push(await parseFile(file))
  }
  return results
}

export async function parseFile(file: File): Promise<ParsedFileMeta> {
  const type = detectFileType(file.name)
  if (!SUPPORTED_TYPES.has(type)) {
    throw new Error(`不支持的文件类型: ${type}`)
  }

  let content = ''
  if (type === 'pdf') {
    content = await parsePdf(file)
  } else if (type === 'docx') {
    content = await parseDocx(file)
  } else {
    content = await parseText(file)
  }

  return {
    fileId: `file_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
    name: file.name,
    type,
    size: file.size,
    parsedAt: new Date().toISOString(),
    content,
  }
}

export async function saveParsedFiles(files: ParsedFileMeta[]): Promise<ParsedFileMeta[]> {
  if (!files.length) {
    return []
  }
  const payload = {
    files: files.map((file) => ({
      fileId: file.fileId,
      name: file.name,
      type: file.type,
      content: file.content || '',
      size: file.size,
      parsedAt: file.parsedAt,
      url: file.url,
    })),
  }
  const response = await apiRequest<{
    data: Array<{
      fileId: string
      name: string
      type: string
      size: number
      parsedAt: string
      url?: string
      truncated?: boolean
    }>
  }>('/v1/parsed-files/batch', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.data.map((item) => ({
    fileId: item.fileId,
    name: item.name,
    type: item.type,
    size: item.size,
    parsedAt: item.parsedAt,
    url: item.url,
    truncated: item.truncated,
  }))
}

export async function loadParsedFiles(includeContent = true): Promise<ParsedFileMeta[]> {
  const response = await apiRequest<{ data: any[] }>(
    `/v1/parsed-files?include_content=${includeContent ? 'true' : 'false'}`,
  )
  return response.data.map((item) => ({
    fileId: item.fileId,
    name: item.name,
    type: item.type,
    size: item.size,
    parsedAt: item.parsedAt,
    url: item.url,
    content: item.content,
    truncated: item.truncated,
  }))
}

export async function deleteParsedFile(fileId: string): Promise<void> {
  await apiRequest(`/v1/parsed-files/${encodeURIComponent(fileId)}`, { method: 'DELETE' })
}

async function parsePdf(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const pdf = await pdfjsLib.getDocument({ data: buffer }).promise
  let result = ''
  for (let pageNo = 1; pageNo <= pdf.numPages; pageNo += 1) {
    const page = await pdf.getPage(pageNo)
    const content = await page.getTextContent()
    const pageText = content.items
      .map((item) => ('str' in item ? item.str : ''))
      .join(' ')
    result += `${pageText}\n\n`
  }
  return cleanText(result)
}

async function parseDocx(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const result = await mammoth.extractRawText({ arrayBuffer: buffer })
  return cleanText(result.value)
}

async function parseText(file: File): Promise<string> {
  const content = await file.text()
  return cleanText(content)
}

function detectFileType(name: string): string {
  const extension = name.split('.').pop()?.toLowerCase() || ''
  return extension === 'markdown' ? 'md' : extension
}

function cleanText(text: string): string {
  return text
    .replace(/\u200b/g, '')
    .replace(/-\n/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n[ \t]+/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

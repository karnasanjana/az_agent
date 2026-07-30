import { getNodesBounds, type Node, type Edge } from '@xyflow/react'
import type { TableNodeData, RelationshipEdgeData } from '@/types/diagram'
import type { ForeignKey } from '@/types/schema'

interface ExportMetadata {
  databaseName: string
  tableCount: number
  relationshipCount: number
  foreignKeys?: ForeignKey[]
}

// Layout constants
const BOUNDS_PADDING = 60
const HEADER_HEIGHT = 28
const COL_ROW_HEIGHT = 16
const COL_FONT_SIZE = 10
const TABLE_MIN_WIDTH = 160
const CHAR_WIDTH = 6.2 // approximate monospace char width at 10px

// Dataset color map (matching frontend palette)
const DEFAULT_HEADER_COLOR = '#3B82F6'
const DEFAULT_HEADER_TEXT = '#FFFFFF'

/**
 * Export the ER diagram as a PDF using pure SVG generation.
 * No DOM rasterization — builds SVG from node/edge data directly.
 */
export async function exportDiagramAsPdf(
  getNodes: () => Node[],
  metadata: ExportMetadata,
  edges?: Edge<RelationshipEdgeData>[]
): Promise<void> {
  const nodes = getNodes() as Node<TableNodeData>[]
  if (nodes.length === 0) return

  const nodesBounds = getNodesBounds(nodes)
  const bounds = {
    x: nodesBounds.x - BOUNDS_PADDING,
    y: nodesBounds.y - BOUNDS_PADDING,
    width: nodesBounds.width + BOUNDS_PADDING * 2,
    height: nodesBounds.height + BOUNDS_PADDING * 2,
  }

  // Build SVG string from nodes and edges
  const svgContent = buildSvg(nodes, edges || [], bounds)

  // Create an SVG DOM element for svg2pdf
  const parser = new DOMParser()
  const svgDoc = parser.parseFromString(svgContent, 'image/svg+xml')
  const svgElement = svgDoc.documentElement

  // Import jsPDF and svg2pdf
  const { jsPDF } = await import('jspdf')
  const { svg2pdf } = await import('svg2pdf.js')

  const doc = new jsPDF({
    orientation: bounds.width > bounds.height ? 'landscape' : 'portrait',
    unit: 'mm',
    format: 'a4',
  })

  const pageWidth = doc.internal.pageSize.getWidth()
  const pageHeight = doc.internal.pageSize.getHeight()
  const margin = 10
  const dateStr = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })

  // Header
  doc.setFontSize(14)
  doc.setTextColor(0, 0, 0)
  doc.text(metadata.databaseName, margin, margin + 5)

  doc.setFontSize(9)
  doc.setTextColor(128, 128, 128)
  doc.text(
    `${metadata.tableCount} tables | ${metadata.relationshipCount} relationships | ${dateStr}`,
    margin,
    margin + 10
  )

  // Calculate fit
  const imageY = margin + 14
  const availableWidth = pageWidth - margin * 2
  const availableHeight = pageHeight - imageY - margin

  const scaleX = availableWidth / bounds.width
  const scaleY = availableHeight / bounds.height
  const scale = Math.min(scaleX, scaleY)

  const imgW = bounds.width * scale
  const imgH = bounds.height * scale

  // Center horizontally
  const imgX = margin + (availableWidth - imgW) / 2

  // Embed SVG into PDF
  await svg2pdf(svgElement, doc, {
    x: imgX,
    y: imageY,
    width: imgW,
    height: imgH,
  })

  // === Relationship Reference Pages ===
  if (metadata.foreignKeys && metadata.foreignKeys.length > 0) {
    addRelationshipPages(doc, metadata.foreignKeys, metadata.databaseName, margin)
  }

  const fileName = `${metadata.databaseName.replace(/[^a-zA-Z0-9]/g, '_')}_ER_Diagram.pdf`
  doc.save(fileName)
}

/**
 * Add relationship reference table pages to the PDF.
 */
function addRelationshipPages(
  doc: InstanceType<typeof import('jspdf').jsPDF>,
  foreignKeys: ForeignKey[],
  databaseName: string,
  margin: number
): void {
  const pageWidth = doc.internal.pageSize.getWidth()
  const pageHeight = doc.internal.pageSize.getHeight()

  // Separate intra-DB and cross-DB relationships
  const intraDb: ForeignKey[] = []
  const crossDb: ForeignKey[] = []
  for (const fk of foreignKeys) {
    if (fk.source_schema === fk.target_schema) {
      intraDb.push(fk)
    } else {
      crossDb.push(fk)
    }
  }

  // Sort alphabetically by constraint name
  intraDb.sort((a, b) => a.constraint_name.localeCompare(b.constraint_name))
  crossDb.sort((a, b) => a.constraint_name.localeCompare(b.constraint_name))

  // Table layout
  const colWidths = {
    num: 8,
    name: 52,
    sourceTable: 40,
    sourceCol: 35,
    targetTable: 40,
    targetCol: 35,
    type: 18,
  }
  const tableX = margin
  const rowHeight = 6
  const headerRowHeight = 7
  const sectionGap = 10

  let y = 0
  let pageNum = 0

  function startNewPage() {
    doc.addPage('a4', 'landscape')
    pageNum++
    y = margin

    // Page header
    doc.setFontSize(12)
    doc.setTextColor(0, 0, 0)
    doc.text(`${databaseName} — Relationship Reference`, margin, y + 4)

    doc.setFontSize(8)
    doc.setTextColor(128, 128, 128)
    doc.text(
      `${foreignKeys.length} relationships (${intraDb.length} intra-database, ${crossDb.length} cross-database)`,
      margin,
      y + 9
    )

    y += 14
  }

  function drawTableHeader() {
    if (y + headerRowHeight + rowHeight > pageHeight - margin) {
      startNewPage()
    }

    // Header background
    doc.setFillColor(241, 245, 249) // slate-100
    doc.rect(tableX, y, pageWidth - margin * 2, headerRowHeight, 'F')

    // Header border
    doc.setDrawColor(203, 213, 225) // slate-300
    doc.setLineWidth(0.3)
    doc.rect(tableX, y, pageWidth - margin * 2, headerRowHeight, 'S')

    doc.setFontSize(7)
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(51, 65, 85) // slate-700

    let x = tableX + 2
    doc.text('#', x, y + 4.5)
    x += colWidths.num
    doc.text('Relationship Name', x, y + 4.5)
    x += colWidths.name
    doc.text('Source Table', x, y + 4.5)
    x += colWidths.sourceTable
    doc.text('Source Column(s)', x, y + 4.5)
    x += colWidths.sourceCol
    doc.text('Target Table', x, y + 4.5)
    x += colWidths.targetTable
    doc.text('Target Column(s)', x, y + 4.5)
    x += colWidths.targetCol
    doc.text('Type', x, y + 4.5)

    y += headerRowHeight
  }

  function drawRow(fk: ForeignKey, index: number, isCrossDb: boolean) {
    if (y + rowHeight > pageHeight - margin) {
      startNewPage()
      drawTableHeader()
    }

    // Alternating row background
    if (index % 2 === 0) {
      doc.setFillColor(248, 250, 252) // slate-50
      doc.rect(tableX, y, pageWidth - margin * 2, rowHeight, 'F')
    }

    // Row border
    doc.setDrawColor(226, 232, 240) // slate-200
    doc.setLineWidth(0.2)
    doc.line(tableX, y + rowHeight, tableX + pageWidth - margin * 2, y + rowHeight)

    doc.setFontSize(7)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(71, 85, 105) // slate-600

    let x = tableX + 2
    doc.text(String(index + 1), x, y + 4)
    x += colWidths.num

    // Constraint name (truncate if too long)
    const nameText = truncate(fk.constraint_name, 38)
    doc.text(nameText, x, y + 4)
    x += colWidths.name

    // Source table
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(30, 41, 59) // slate-800
    doc.text(truncate(`${fk.source_schema}.${fk.source_table}`, 28), x, y + 4)
    x += colWidths.sourceTable

    // Source columns
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(71, 85, 105)
    doc.text(truncate(fk.source_columns.join(', '), 24), x, y + 4)
    x += colWidths.sourceCol

    // Target table
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(30, 41, 59)
    doc.text(truncate(`${fk.target_schema}.${fk.target_table}`, 28), x, y + 4)
    x += colWidths.targetTable

    // Target columns
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(71, 85, 105)
    doc.text(truncate(fk.target_columns.join(', '), 24), x, y + 4)
    x += colWidths.targetCol

    // Type badge
    if (isCrossDb) {
      doc.setFillColor(219, 234, 254) // blue-100
      doc.roundedRect(x - 1, y + 0.5, 16, 4.5, 1, 1, 'F')
      doc.setFontSize(6)
      doc.setTextColor(37, 99, 235) // blue-600
      doc.text('Cross-DB', x + 1, y + 3.8)
    } else {
      doc.setFontSize(6)
      doc.setTextColor(100, 116, 139) // slate-500
      doc.text('Intra-DB', x + 1, y + 3.8)
    }

    y += rowHeight
  }

  // Start first reference page
  startNewPage()

  // Intra-database relationships
  if (intraDb.length > 0) {
    doc.setFontSize(9)
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(30, 41, 59)
    doc.text(`Within Database (${intraDb.length})`, margin, y + 3)
    y += 6

    drawTableHeader()
    intraDb.forEach((fk, i) => drawRow(fk, i, false))
  }

  // Cross-database relationships
  if (crossDb.length > 0) {
    y += sectionGap

    if (y + headerRowHeight + rowHeight * 2 > pageHeight - margin) {
      startNewPage()
    }

    doc.setFontSize(9)
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(30, 41, 59)
    doc.text(`Cross-Database (${crossDb.length})`, margin, y + 3)
    y += 6

    drawTableHeader()
    crossDb.forEach((fk, i) => drawRow(fk, i, true))
  }
}

function truncate(str: string, maxLen: number): string {
  return str.length > maxLen ? str.slice(0, maxLen - 1) + '…' : str
}

/**
 * Build a complete SVG string from React Flow nodes and edges.
 */
function buildSvg(
  nodes: Node<TableNodeData>[],
  edges: Edge<RelationshipEdgeData>[],
  bounds: { x: number; y: number; width: number; height: number }
): string {
  const parts: string[] = []

  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" ` +
    `viewBox="${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}" ` +
    `width="${bounds.width}" height="${bounds.height}">`
  )

  // Background
  parts.push(`<rect x="${bounds.x}" y="${bounds.y}" width="${bounds.width}" height="${bounds.height}" fill="#ffffff"/>`)

  // Defs for filters
  parts.push(`<defs>
    <filter id="shadow" x="-4%" y="-4%" width="108%" height="108%">
      <feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000" flood-opacity="0.1"/>
    </filter>
  </defs>`)

  // Build node lookup for edge routing
  const nodeMap = new Map<string, { x: number; y: number; width: number; height: number }>()
  for (const node of nodes) {
    const cols = (node.data as TableNodeData).columns || []
    const w = Math.max(TABLE_MIN_WIDTH, node.measured?.width || estimateWidth(node.data as TableNodeData))
    const h = HEADER_HEIGHT + cols.length * COL_ROW_HEIGHT + 8
    nodeMap.set(node.id, {
      x: node.position.x,
      y: node.position.y,
      width: w,
      height: h,
    })
  }

  // Draw edges first (behind nodes)
  for (const edge of edges) {
    const sourceRect = nodeMap.get(edge.source)
    const targetRect = nodeMap.get(edge.target)
    if (!sourceRect || !targetRect) continue

    const color = (edge.data as RelationshipEdgeData)?.color || '#94A3B8'
    const { sx, sy, tx, ty } = getEdgePoints(sourceRect, targetRect)

    // Smoothstep-like path
    const midY = (sy + ty) / 2
    parts.push(
      `<path d="M ${sx} ${sy} C ${sx} ${midY}, ${tx} ${midY}, ${tx} ${ty}" ` +
      `fill="none" stroke="${color}" stroke-width="1.5" opacity="0.7"/>`
    )
  }

  // Draw nodes
  for (const node of nodes) {
    const data = node.data as TableNodeData
    const rect = nodeMap.get(node.id)!
    parts.push(buildTableSvg(data, rect))
  }

  parts.push('</svg>')
  return parts.join('\n')
}

/**
 * Build SVG for a single table node.
 */
function buildTableSvg(
  data: TableNodeData,
  rect: { x: number; y: number; width: number; height: number }
): string {
  const { x, y, width: w } = rect
  const columns = data.columns || []
  const h = HEADER_HEIGHT + columns.length * COL_ROW_HEIGHT + 8
  const headerColor = data.datasetColor || DEFAULT_HEADER_COLOR
  const displayName = `${data.table_name} (${data.schema_name})`

  const parts: string[] = []

  // Table card with shadow
  parts.push(`<g filter="url(#shadow)">`)
  // Card background
  parts.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="#ffffff" stroke="#E2E8F0" stroke-width="1"/>`)
  // Header
  parts.push(`<rect x="${x}" y="${y}" width="${w}" height="${HEADER_HEIGHT}" rx="6" fill="${headerColor}"/>`)
  parts.push(`<rect x="${x}" y="${y + HEADER_HEIGHT - 6}" width="${w}" height="6" fill="${headerColor}"/>`)
  // Header text
  parts.push(`<text x="${x + 10}" y="${y + 18}" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="${DEFAULT_HEADER_TEXT}">${escapeXml(displayName)}</text>`)

  // Columns
  let cy = y + HEADER_HEIGHT + 4
  for (const col of columns) {
    const isPk = col.is_primary_key
    const isFk = data.fkColumns?.has?.(col.name) || false
    const isNullable = col.is_nullable

    // Icons
    let iconX = x + 6
    if (isPk) {
      parts.push(`<text x="${iconX}" y="${cy + 11}" font-size="9" fill="#F59E0B" title="PK">🔑</text>`)
      iconX += 14
    }
    if (isFk) {
      parts.push(`<text x="${iconX}" y="${cy + 11}" font-size="9" fill="#3B82F6" title="FK">🔗</text>`)
      iconX += 14
    }

    // Column name
    const textX = isPk || isFk ? iconX + 2 : x + 10
    const fontWeight = isPk ? 'bold' : 'normal'
    parts.push(`<text x="${textX}" y="${cy + 11}" font-family="Arial, sans-serif" font-size="${COL_FONT_SIZE}" font-weight="${fontWeight}" fill="#334155">${escapeXml(col.name)}</text>`)

    // Nullable indicator
    if (isNullable) {
      parts.push(`<text x="${x + w - 14}" y="${cy + 11}" font-family="Arial, sans-serif" font-size="9" fill="#CBD5E1">?</text>`)
    }

    cy += COL_ROW_HEIGHT
  }

  parts.push('</g>')
  return parts.join('\n')
}

/**
 * Calculate edge connection points between two table rectangles.
 */
function getEdgePoints(
  source: { x: number; y: number; width: number; height: number },
  target: { x: number; y: number; width: number; height: number }
) {
  const sCx = source.x + source.width / 2
  const sCy = source.y + source.height / 2
  const tCx = target.x + target.width / 2
  const tCy = target.y + target.height / 2

  // Connect from bottom of source to top of target (or vice versa)
  let sx: number, sy: number, tx: number, ty: number

  if (sCy < tCy) {
    // Source is above target
    sx = sCx
    sy = source.y + source.height
    tx = tCx
    ty = target.y
  } else {
    // Source is below target
    sx = sCx
    sy = source.y
    tx = tCx
    ty = target.y + target.height
  }

  return { sx, sy, tx, ty }
}

/**
 * Estimate table width from column names.
 */
function estimateWidth(data: TableNodeData): number {
  const headerLen = `${data.table_name} (${data.schema_name})`.length
  const maxColLen = Math.max(...(data.columns || []).map((c) => c.name.length), 0)
  const maxChars = Math.max(headerLen, maxColLen + 6) // +6 for icons and padding
  return Math.max(TABLE_MIN_WIDTH, maxChars * CHAR_WIDTH + 30)
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

import type { Receipt } from '../lib/analytics';

export function CalculationReceipt({receipt}:{receipt:Receipt & {report_revision?:number}}) {
  return <details className="calculation-receipt"><summary>How was this calculated?</summary>
    <p>{receipt.description}</p>
    <p><strong>{receipt.included_rows} included · {receipt.excluded_rows} excluded</strong> out of {receipt.total_rows} source rows.</p>
    <p>Excluded by filters: {receipt.excluded_by_filters} · Missing selected value: {receipt.excluded_missing_value} · Outside table limit: {receipt.excluded_by_limit}</p>
    {receipt.queries.map((query,index)=><div key={index}><pre>{query.sql}</pre><p>Bound parameters: <code>{JSON.stringify(query.parameters)}</code></p></div>)}
    <p>{receipt.postprocessing}</p><p>{receipt.source_relation}</p>
    <p>Column mapping: {receipt.column_mapping.map(column=>`${column.key} = ${column.name} (${column.sql_type})`).join('; ')}</p>
    <p className="csv-version">Dataset SHA-256: <code>{receipt.dataset_sha256}</code><br />{receipt.parser_version} · {receipt.calculation_version}{receipt.report_revision!==undefined&&<> · Report revision {receipt.report_revision}</>}</p>
  </details>;
}

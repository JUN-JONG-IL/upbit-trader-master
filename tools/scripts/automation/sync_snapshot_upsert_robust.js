/**
 * sync_snapshot_upsert_robust.js
 * - 읽을 파일: /tmp/snapshot_rows.jsonl
 * - BOM(UTF-8/UTF-16 LE/BE)을 감지/제거하여 문자열로 디코딩
 * - 줄 단위로 JSON 파싱 (psql row_to_json 래퍼 처리)
 * - last_time, updated_at: epoch 숫자 또는 ISO 문자열을 Date로 변환
 * - symbol+timeframe 기준으로 upsert (updateOne with upsert)
 * - 여러번 실행해도 안전하도록, 변경할 필드가 없으면 스킵
 */
const fs = require('fs');

function decodeBuffer(buf) {
  if (!buf || buf.length === 0) return '';
  // UTF-8 BOM
  if (buf.length >= 3 && buf[0] === 0xEF && buf[1] === 0xBB && buf[2] === 0xBF) {
    return buf.slice(3).toString('utf8');
  }
  // UTF-16 LE BOM
  if (buf.length >= 2 && buf[0] === 0xFF && buf[1] === 0xFE) {
    return buf.slice(2).toString('utf16le');
  }
  // UTF-16 BE BOM: swap bytes then decode as utf16le
  if (buf.length >= 2 && buf[0] === 0xFE && buf[1] === 0xFF) {
    const src = buf.slice(2);
    const swapped = Buffer.alloc(src.length);
    for (let i = 0; i + 1 < src.length; i += 2) {
      swapped[i] = src[i + 1];
      swapped[i + 1] = src[i];
    }
    if (src.length % 2 === 1) swapped[swapped.length - 1] = src[src.length - 1];
    return swapped.toString('utf16le');
  }
  // default UTF-8
  return buf.toString('utf8');
}

try {
  const path = '/tmp/snapshot_rows.jsonl';
  if (!fs.existsSync(path)) {
    print("ERROR: file not found: " + path);
    quit(1);
  }

  const rawBuf = fs.readFileSync(path);
  const raw = decodeBuffer(rawBuf).trim();
  if (!raw) {
    print("INFO: file empty: " + path);
    quit(0);
  }

  const lines = raw.split(/\r?\n/);
  const dbname = 'upbit_trader';
  const coll = db.getSiblingDB(dbname).latest_snapshot;

  let processed = 0;
  let skipped = 0;
  let parseErrors = 0;

  for (let i = 0; i < lines.length; i++) {
    const lineNo = i + 1;
    const line = lines[i].trim();
    if (!line) { skipped++; continue; }

    let parsed;
    try {
      parsed = JSON.parse(line);
    } catch (e) {
      print(`WARN: JSON parse failed line ${lineNo}: ${e}`);
      parseErrors++;
      continue;
    }

    const doc = parsed.row_to_json ? parsed.row_to_json : parsed;
    if (!doc || !doc.symbol || !doc.timeframe) {
      print(`WARN: missing required fields, skip line ${lineNo}: ${JSON.stringify(doc)}`);
      skipped++;
      continue;
    }

    // Normalize date fields to JS Date
    let last_time = null;
    let updated_at = null;

    if (doc.last_time_epoch !== undefined && doc.last_time_epoch !== null) {
      last_time = new Date(Number(doc.last_time_epoch) * 1000);
    } else if (doc.last_time !== undefined && doc.last_time !== null) {
      if (typeof doc.last_time === 'number') {
        last_time = new Date(Number(doc.last_time) * 1000);
      } else if (typeof doc.last_time === 'string') {
        const d = new Date(doc.last_time);
        if (!isNaN(d)) last_time = d;
      }
    }

    if (doc.updated_at_epoch !== undefined && doc.updated_at_epoch !== null) {
      updated_at = new Date(Number(doc.updated_at_epoch) * 1000);
    } else if (doc.updated_at !== undefined && doc.updated_at !== null) {
      if (typeof doc.updated_at === 'number') {
        updated_at = new Date(Number(doc.updated_at) * 1000);
      } else if (typeof doc.updated_at === 'string') {
        const d2 = new Date(doc.updated_at);
        if (!isNaN(d2)) updated_at = d2;
      }
    }

    const filter = { symbol: doc.symbol, timeframe: doc.timeframe };
    const setObj = {};
    if (last_time) setObj.last_time = last_time;
    if (updated_at) setObj.updated_at = updated_at;

    // skip if nothing to set (avoid empty upserts)
    if (Object.keys(setObj).length === 0) {
      print(`WARN: nothing to set for ${JSON.stringify(filter)}, skip line ${lineNo}`);
      skipped++;
      continue;
    }

    const res = coll.updateOne(filter, { $set: setObj }, { upsert: true });
    print(`Upserted: ${JSON.stringify(filter)} -> matched:${res.matchedCount} modified:${res.modifiedCount} upsertedId:${res.upsertedId ? res.upsertedId._id : ""}`);
    processed++;
  }

  print(`SYNC COMPLETE. processed lines: ${processed}, skipped: ${skipped}, parseErrors: ${parseErrors}`);
  quit(0);
} catch (e) {
  print("FATAL ERROR: " + e);
  quit(2);
}
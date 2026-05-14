# flush_all.ps1
$count = 0
$max = 10

while ($count -lt $max) {
    $count++
    Write-Host "`n=== 실행 $count/$max ===" -ForegroundColor Cyan
    python manual_flush_dedup.py
    
    # Staging 건수 확인
    $staging = (python -c "import psycopg2; conn=psycopg2.connect(host='127.0.0.1',port=58529,database='upbit_trader',user='postgres',password='postgres'); cur=conn.cursor(); cur.execute('SELECT COUNT(*) FROM staging_candles'); print(cur.fetchone()[0])")
    
    Write-Host "Staging 남음: $staging 개" -ForegroundColor Yellow
    
    if ([int]$staging -lt 100) {
        Write-Host "`n✅ 완료! (Staging < 100)" -ForegroundColor Green
        break
    }
    
    Start-Sleep -Seconds 2
}

Write-Host "`n🎉 전체 Flush 완료!" -ForegroundColor Green
python check_staging_data.py
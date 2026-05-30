#!/bin/bash
# backup.sh — резервное копирование SQLite и файлов
# Запускайте через cron: 0 3 * * * /path/to/backup.sh

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="./backups/$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

# 1. Безопасная копия БД через SQLite online backup
sqlite3 bot.db ".backup $BACKUP_DIR/bot.db"

# 2. Копирование директорий с файлами
cp -r files/ "$BACKUP_DIR/files/" 2>/dev/null || true
cp -r checklists/ "$BACKUP_DIR/checklists/" 2>/dev/null || true
cp -r submissions/ "$BACKUP_DIR/submissions/" 2>/dev/null || true

# 3. Упаковать в архив
tar -czf "./backups/backup_$TIMESTAMP.tar.gz" -C "./backups" "$TIMESTAMP"
rm -rf "$BACKUP_DIR"

# 4. Оставлять только последние 7 резервных копий
ls -t ./backups/backup_*.tar.gz 2>/dev/null | tail -n +8 | xargs rm -f

echo "✅ Backup created: backups/backup_$TIMESTAMP.tar.gz"

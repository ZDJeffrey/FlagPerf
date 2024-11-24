ls | grep -v driver | while read dir; do
    if [ -d "$dir/metax/C550_64" ]; then
        mkdir -p "$dir/metax/C500" # 创建目标文件夹
        # 使用 rsync 复制文件并排除 README.md
        rsync -av --exclude='README.md' "$dir/metax/C550_64/" "$dir/metax/C500/"
    fi
done

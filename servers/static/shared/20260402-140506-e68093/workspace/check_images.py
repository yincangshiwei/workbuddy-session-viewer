from openpyxl import load_workbook
import sys

sys.stdout.reconfigure(encoding='utf-8')

def check_images_in_sheet(sheet_name):
    print(f"\n=== Sheet: {sheet_name} ===")
    wb = load_workbook('Lenta 2025圣诞自留版.xlsx')
    sheet = wb[sheet_name]
    
    print(f"图片数量: {len(sheet._images)}")
    
    for idx, img in enumerate(sheet._images):
        print(f"\n  图片 {idx + 1}:")
        print(f"    文件: {img.ref}")
        if hasattr(img.anchor, '_from') and img.anchor._from:
            print(f"    位置: 行{img.anchor._from.row + 1}, 列{img.anchor._from.col + 1}")
        else:
            print(f"    位置: 未知")
    
    wb.close()

# 检查所有需要的sheet
for sheet_name in ["塑料球", "外厂", "陶瓷"]:
    check_images_in_sheet(sheet_name)

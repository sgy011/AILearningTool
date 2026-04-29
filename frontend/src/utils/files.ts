/** 将 File[] 转为可与原有 `<input type="file">` change 逻辑兼容的 FileList */
export function toFileList(files: File[]): FileList {
  const dt = new DataTransfer()
  files.forEach((f) => dt.items.add(f))
  return dt.files
}

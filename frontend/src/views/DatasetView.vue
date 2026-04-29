<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import ToolPageShell from '../components/ToolPageShell.vue'
import { datasetProcess, datasetProcessLocal } from '../api/dataset'
import { launchLabelImg } from '../api/labelimg'
import { downloadBlob } from '../api/download'
import { normalizeApiError } from '../api/http'
import FileDropZone from '../components/FileDropZone.vue'

const zip = ref<File | null>(null)
const inFormat = ref<'auto' | 'yolo' | 'coco' | 'voc'>('auto')
const outFormat = ref<'yolo' | 'coco' | 'voc'>('yolo')
const train = ref(0.8)
const val = ref(0.2)
const test = ref(0)
const seed = ref(42)
const name = ref('')
const busy = ref(false)

// 本地目录模式
const imagesDir = ref('')
const labelsDir = ref('')
const labelBusy = ref(false)
const useLocalMode = ref(true) // 默认使用本地目录模式

async function onLaunchLabelImg() {
  if (!imagesDir.value.trim()) return ElMessage.error('请填写图片目录')
  labelBusy.value = true
  try {
    const d = await launchLabelImg({ images_dir: imagesDir.value.trim(), save_dir: labelsDir.value.trim() || undefined })
    if (!d.success) throw new Error(d.error || '启动失败')
    ElMessage.success('LabelImg 已启动（本机）')
  } catch (e) {
    ElMessage.error(normalizeApiError(e).message)
  } finally {
    labelBusy.value = false
  }
}

async function run() {
  if (useLocalMode.value) {
    // 本地目录模式：使用 images_dir 和 labels_dir
    if (!imagesDir.value.trim()) return ElMessage.error('请填写图片目录')
    busy.value = true
    try {
      const blob = await datasetProcessLocal({
        images_dir: imagesDir.value.trim(),
        labels_dir: labelsDir.value.trim() || undefined,
        in_format: inFormat.value,
        out_format: outFormat.value,
        train: train.value,
        val: val.value,
        test: test.value,
        seed: seed.value,
        name: name.value.trim() || undefined,
      })
      downloadBlob(blob, `${name.value.trim() || 'dataset_out'}.zip`)
      ElMessage.success('已开始下载')
    } catch (e) {
      ElMessage.error(normalizeApiError(e).message)
    } finally {
      busy.value = false
    }
  } else {
    // ZIP 模式
    if (!zip.value) return ElMessage.error('请上传数据集 zip')
    busy.value = true
    try {
      const blob = await datasetProcess({
        zip: zip.value,
        in_format: inFormat.value,
        out_format: outFormat.value,
        train: train.value,
        val: val.value,
        test: test.value,
        seed: seed.value,
        name: name.value.trim() || undefined,
      })
      downloadBlob(blob, `${name.value.trim() || 'dataset_out'}.zip`)
      ElMessage.success('已开始下载')
    } catch (e) {
      ElMessage.error(normalizeApiError(e).message)
    } finally {
      busy.value = false
    }
  }
}
</script>

<template>
  <ToolPageShell
    title="数据标注划分"
    subtitle="启动 LabelImg 标注，并完成格式转换与训练集划分，输出可直接用于训练。"
  >
    <div class="mode-tabs">
      <el-radio-group v-model="useLocalMode">
        <el-radio-button :value="true">使用本地目录（LabelImg 标注后）</el-radio-button>
        <el-radio-button :value="false">上传 ZIP 数据集</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 本地目录模式 -->
    <div v-if="useLocalMode" class="label-section">
      <div class="section-label">第一步：使用 LabelImg 标注图片</div>
      <el-row :gutter="12" style="margin-bottom: 8px">
        <el-col :span="12">
          <div class="label">图片目录 <span class="required">*</span></div>
          <div style="display: flex; gap: 6px">
            <el-input v-model="imagesDir" placeholder="粘贴完整路径，如 D:\dataset\images" style="flex: 1" />
          </div>
        </el-col>
        <el-col :span="12">
          <div class="label">标注保存目录（可选，留空则自动查找）</div>
          <div style="display: flex; gap: 6px">
            <el-input v-model="labelsDir" placeholder="粘贴完整路径，如 D:\dataset\labels" style="flex: 1" />
          </div>
        </el-col>
      </el-row>
      <div class="tip-text">
        💡 提示：标注目录通常与图片目录平级，如 images/ 和 labels/ 在同一父目录下
      </div>
      <div class="actions">
        <el-button type="primary" :loading="labelBusy" @click="onLaunchLabelImg">启动 LabelImg</el-button>
      </div>
    </div>

    <!-- ZIP 模式 -->
    <template v-if="!useLocalMode">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
        上传包含 images/ 与 labels/annotations 的 zip，支持标注格式转换（YOLO/COCO/VOC）并划分 train/val/test，输出 zip 下载。
      </el-alert>

      <div style="margin-bottom: 12px">
        <div class="label">数据集压缩包（.zip）</div>
        <FileDropZone
          accept=".zip"
          :multiple="false"
          title="拖拽 .zip 到此处"
          description="单个压缩包；也可点击选择文件"
          @select="(files) => { zip = files[0] || null }"
        />
      </div>
    </template>

    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      第二步：选择输出格式并划分训练集
    </el-alert>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="12">
        <div class="label">输入标注格式</div>
        <el-select v-model="inFormat" style="width: 100%">
          <el-option value="auto" label="自动识别" />
          <el-option value="yolo" label="YOLO（txt）" />
          <el-option value="coco" label="COCO（json）" />
          <el-option value="voc" label="Pascal VOC（xml）" />
        </el-select>
      </el-col>
      <el-col :span="12">
        <div class="label">输出标注格式</div>
        <el-select v-model="outFormat" style="width: 100%">
          <el-option value="yolo" label="YOLO（txt）" />
          <el-option value="coco" label="COCO（json）" />
          <el-option value="voc" label="Pascal VOC（xml）" />
        </el-select>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="8">
        <div class="label">train</div>
        <el-input-number v-model="train" :min="0" :max="1" :step="0.01" style="width: 100%" />
      </el-col>
      <el-col :span="8">
        <div class="label">val</div>
        <el-input-number v-model="val" :min="0" :max="1" :step="0.01" style="width: 100%" />
      </el-col>
      <el-col :span="8">
        <div class="label">test</div>
        <el-input-number v-model="test" :min="0" :max="1" :step="0.01" style="width: 100%" />
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-bottom: 12px">
      <el-col :span="8">
        <div class="label">随机种子</div>
        <el-input-number v-model="seed" :min="0" :step="1" style="width: 100%" />
      </el-col>
      <el-col :span="16">
        <div class="label">输出包名（可选）</div>
        <el-input v-model="name" placeholder="dataset_out（默认）" />
      </el-col>
    </el-row>

    <div class="actions">
      <el-button type="primary" :loading="busy" @click="run">转换并划分</el-button>
    </div>
  </ToolPageShell>
</template>

<style scoped>
.mode-tabs {
  margin-bottom: 16px;
  display: flex;
  justify-content: center;
}
.label-section {
  background: linear-gradient(135deg, #f0f7ff, #e8f4fd);
  border: 1px solid rgba(80, 176, 240, 0.2);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 14px;
}
.section-label {
  font-size: 14px;
  font-weight: 600;
  color: #0a2a4a;
  margin-bottom: 10px;
}
.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 8px 0 6px;
}
.required {
  color: #f56c6c;
}
.tip-text {
  font-size: 12px;
  color: #606266;
  background: #fdf6ec;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 10px;
  line-height: 1.5;
}
.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>

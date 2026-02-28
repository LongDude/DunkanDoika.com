<template>
  <section class="card">
    <h2>{{ t('presets.title') }}</h2>

    <div class="row">
      <input v-model.trim="newPresetName" :placeholder="t('presets.namePlaceholder')" />
      <button :disabled="editor.presetsSaving.value" @click="createPreset">
        {{ t('presets.createFromCurrent') }}
      </button>
      <button :disabled="selectedIds.length === 0 || editor.presetsSaving.value" @click="bulkDelete">
        {{ t('presets.bulkDelete') }}
      </button>
    </div>

    <p v-if="editor.presetsLoading.value" class="muted">{{ t('common.loading') }}</p>
    <p v-else-if="editor.userPresets.value.length === 0" class="muted">{{ t('presets.empty') }}</p>

    <div v-else class="table-wrap">
      <table class="presets-table">
        <thead>
          <tr>
            <th class="presets-col-check">
              <input type="checkbox" :checked="allSelected" @change="toggleSelectAll" />
            </th>
            <th class="presets-col-name">{{ t('presets.name') }}</th>
            <th class="presets-col-updated">{{ t('presets.updatedAt') }}</th>
            <th class="presets-col-actions">{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="preset in editor.userPresets.value" :key="preset.preset_id">
            <td>
              <input
                type="checkbox"
                :checked="selectedIds.includes(preset.preset_id)"
                @change="toggleSelected(preset.preset_id)"
              />
            </td>
            <td>{{ preset.name }}</td>
            <td>{{ formatDate(preset.updated_at, localeAsApp) }}</td>
            <td class="presets-actions-cell">
              <div class="row-actions preset-actions">
                <button @click="applyPreset(preset.preset_id)">{{ t('presets.apply') }}</button>
                <button @click="updatePresetParams(preset.preset_id)">{{ t('presets.updateFromCurrent') }}</button>
                <button @click="renamePreset(preset.preset_id, preset.name)">{{ t('presets.rename') }}</button>
                <button @click="deleteOne(preset.preset_id)">{{ t('common.remove') }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AppLocale } from '../i18n/messages'
import type { ScenarioEditorStore } from '../composables/useScenarioEditor'
import { formatDate } from '../utils/format'

const props = defineProps<{
  editor: ScenarioEditorStore
}>()

const { t, locale } = useI18n()
const newPresetName = ref('')
const selectedIds = ref<string[]>([])

const localeAsApp = computed(() => (locale.value === 'ru' ? 'ru' : 'en') as AppLocale)

const allSelected = computed(
  () =>
    props.editor.userPresets.value.length > 0 &&
    props.editor.userPresets.value.every(item => selectedIds.value.includes(item.preset_id)),
)

function toggleSelected(id: string) {
  if (selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter(x => x !== id)
  } else {
    selectedIds.value = [...selectedIds.value, id]
  }
}

function toggleSelectAll() {
  if (allSelected.value) {
    selectedIds.value = []
    return
  }
  selectedIds.value = props.editor.userPresets.value.map(x => x.preset_id)
}

async function createPreset() {
  if (!newPresetName.value.trim()) return
  try {
    await props.editor.saveCurrentAsUserPreset(newPresetName.value.trim())
    newPresetName.value = ''
    selectedIds.value = []
  } catch (err) {
    alert(`${t('alerts.saveFailed')}: ${err instanceof Error ? err.message : ''}`)
  }
}

function applyPreset(presetId: string) {
  const preset = props.editor.userPresets.value.find(x => x.preset_id === presetId)
  if (!preset) return
  props.editor.applyUserPreset(preset)
}

async function updatePresetParams(presetId: string) {
  try {
    await props.editor.updateUserPresetById(presetId, { replaceParams: true })
  } catch (err) {
    alert(`${t('alerts.saveFailed')}: ${err instanceof Error ? err.message : ''}`)
  }
}

async function renamePreset(presetId: string, currentName: string) {
  const value = window.prompt(t('presets.renamePrompt'), currentName)
  if (!value || !value.trim()) return
  try {
    await props.editor.updateUserPresetById(presetId, { name: value.trim() })
  } catch (err) {
    alert(`${t('alerts.saveFailed')}: ${err instanceof Error ? err.message : ''}`)
  }
}

async function deleteOne(presetId: string) {
  try {
    await props.editor.deleteUserPresetById(presetId)
    selectedIds.value = selectedIds.value.filter(x => x !== presetId)
  } catch (err) {
    alert(`${t('alerts.saveFailed')}: ${err instanceof Error ? err.message : ''}`)
  }
}

async function bulkDelete() {
  try {
    const response = await props.editor.bulkDeleteUserPresetByIds(selectedIds.value)
    selectedIds.value = []
    if (response.skipped.length > 0) {
      alert(
        t('presets.bulkDeleteSummary', {
          deleted: response.deleted_ids.length,
          skipped: response.skipped.length,
        }),
      )
    }
  } catch (err) {
    alert(`${t('alerts.saveFailed')}: ${err instanceof Error ? err.message : ''}`)
  }
}
</script>

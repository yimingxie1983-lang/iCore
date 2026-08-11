

export interface PersonaMeta {
  id: string
  name: string
  aliases: string[]
  icon: string
  color: string
}

export const PERSONA_META: Record<string, PersonaMeta> = {
  master: {
    id: 'master',
    name: 'iCore 主智能体',
    aliases: ['主智能体', '主', '总调度', '主人格', 'master'],
    icon: '🦀',
    color: 'slate',
  },
  clinician: {
    id: 'clinician',
    name: '临床医师人格',
    aliases: ['临床医师', '临床医生', '临床', '医生', '内科', 'clinician'],
    icon: '🩺',
    color: 'rose',
  },
  researcher: {
    id: 'researcher',
    name: '科研型人格',
    aliases: ['科研', '研究员', '研究者', '研究', 'researcher'],
    icon: '🔬',
    color: 'blue',
  },
  data_analyst: {
    id: 'data_analyst',
    name: '数据分析师人格',
    aliases: ['数据分析师', '数据分析', '数据', '分析师', '统计', 'data_analyst', 'analyst'],
    icon: '📊',
    color: 'cyan',
  },
  writer: {
    id: 'writer',
    name: '学术写作人格',
    aliases: ['学术写作', '写作者', '写作', '撰稿', '文档', 'writer'],
    icon: '✍️',
    color: 'amber',
  },
  coder: {
    id: 'coder',
    name: '编码工程师',
    aliases: ['编码工程师', '编码', '工程师', '程序员', 'coder'],
    icon: '💻',
    color: 'purple',
  },
  critical_reviewer: {
    id: 'critical_reviewer',
    name: '仲裁评审员',
    aliases: ['仲裁评审员', '仲裁人', '仲裁', '评审员', '评审', 'critical_reviewer', 'arbiter'],
    icon: '⚖️',
    color: 'indigo',
  },

  med_oncologist: {
    id: 'med_oncologist',
    name: '肿瘤内科',
    aliases: ['肿瘤内科', '肿瘤内科医生', '内科肿瘤', 'medical oncologist', 'med_oncologist'],
    icon: '💊',
    color: 'emerald',
  },
  surgical_oncologist: {
    id: 'surgical_oncologist',
    name: '外科肿瘤',
    aliases: ['外科', '外科肿瘤', '肿瘤外科', '普外', '肝胆外科', '胸外科', 'surgical oncologist', 'surgical_oncologist'],
    icon: '🔪',
    color: 'orange',
  },
  interventional_radiologist: {
    id: 'interventional_radiologist',
    name: '介入科',
    aliases: ['介入科', '介入', '介入放射', 'interventional radiologist', 'interventional_radiologist', 'IR'],
    icon: '🩹',
    color: 'pink',
  },
  radiation_oncologist: {
    id: 'radiation_oncologist',
    name: '放疗科',
    aliases: ['放疗科', '放疗', '放射治疗', '放射肿瘤', 'radiation oncologist', 'radiation_oncologist'],
    icon: '☢️',
    color: 'yellow',
  },
  radiologist: {
    id: 'radiologist',
    name: '影像科',
    aliases: ['影像科', '放射诊断', '影像', '放射科', 'radiologist'],
    icon: '🖼️',
    color: 'sky',
  },
  pathologist: {
    id: 'pathologist',
    name: '病理科',
    aliases: ['病理科', '病理', '病理医师', 'pathologist'],
    icon: '🧪',
    color: 'teal',
  },

  nuclear_medicine: {
    id: 'nuclear_medicine',
    name: '核医学科',
    aliases: ['核医学', '核医学科', 'PET', 'PET/CT', 'PETCT', '核素治疗', 'nuclear medicine', 'nuclear_medicine'],
    icon: '⚛️',
    color: 'violet',
  },
  molecular_pathologist: {
    id: 'molecular_pathologist',
    name: '分子诊断',
    aliases: ['分子诊断', '分子病理', '基因检测', 'NGS', '测序', '基因组', 'molecular pathology', 'molecular_pathologist'],
    icon: '🧬',
    color: 'lime',
  },
  palliative_care: {
    id: 'palliative_care',
    name: '安宁缓和医疗',
    aliases: ['缓和医疗', '安宁疗护', '姑息治疗', '舒缓医疗', '临终关怀', 'palliative care', 'palliative_care', 'supportive care'],
    icon: '🕊️',
    color: 'stone',
  },
  clinical_pharmacist: {
    id: 'clinical_pharmacist',
    name: '临床药师',
    aliases: ['临床药师', '药师', '药学', '药剂科', '用药', 'clinical pharmacist', 'clinical_pharmacist', 'pharmacist'],
    icon: '💉',
    color: 'red',
  },
  genetic_counselor: {
    id: 'genetic_counselor',
    name: '遗传咨询',
    aliases: ['遗传咨询', '遗传', '胚系', '遗传性肿瘤', '家族史', 'genetic counselor', 'genetic_counselor', 'genetics'],
    icon: '🧫',
    color: 'fuchsia',
  },
  nutrition: {
    id: 'nutrition',
    name: '营养科',
    aliases: ['营养科', '营养', '临床营养', '营养支持', '恶病质', 'nutrition', 'dietitian'],
    icon: '🥗',
    color: 'green',
  },
  psycho_oncology: {
    id: 'psycho_oncology',
    name: '精神心理',
    aliases: ['精神心理', '心理科', '精神科', '心理', '心理社会', '精神肿瘤', 'psycho-oncology', 'psycho_oncology', 'psychology'],
    icon: '🫂',
    color: 'violet',
  },

  gastroenterology: {
    id: 'gastroenterology',
    name: '消化内科',
    aliases: ['消化内科', '消化科', '消化', '内镜', '胃肠', 'gastroenterology', 'GI'],
    icon: '🫃',
    color: 'blue',
  },
  gynecologic_oncology: {
    id: 'gynecologic_oncology',
    name: '妇科肿瘤',
    aliases: ['妇科肿瘤', '妇科', '妇瘤', '宫颈', '卵巢', '子宫内膜', 'gynecologic oncology', 'gynecologic_oncology', 'gyn'],
    icon: '🌸',
    color: 'pink',
  },
  reproductive_medicine: {
    id: 'reproductive_medicine',
    name: '生殖医学',
    aliases: ['生殖医学', '生殖科', '生殖', '生育力保存', '肿瘤生殖', '辅助生殖', 'reproductive medicine', 'reproductive_medicine', 'oncofertility'],
    icon: '🍼',
    color: 'rose',
  },
  dermatology_venereology: {
    id: 'dermatology_venereology',
    name: '皮肤性病科',
    aliases: ['皮肤性病科', '皮肤科', '性病科', '皮肤', '性病', 'HPV', '黑色素瘤皮肤', 'dermatology', 'venereology', 'dermatology_venereology'],
    icon: '🧴',
    color: 'amber',
  },
  orthopedic_oncology: {
    id: 'orthopedic_oncology',
    name: '骨科',
    aliases: ['骨科', '骨肿瘤', '骨与软组织', '骨转移', '病理性骨折', 'orthopedic oncology', 'orthopedic_oncology', 'orthopedics'],
    icon: '🦴',
    color: 'stone',
  },
  urology: {
    id: 'urology',
    name: '泌尿外科',
    aliases: ['泌尿外科', '泌尿科', '泌尿', '前列腺', '膀胱', '肾', '睾丸', 'urology', 'urologic oncology'],
    icon: '🚹',
    color: 'sky',
  },
  thoracic_surgery: {
    id: 'thoracic_surgery',
    name: '胸外科',
    aliases: ['胸外科', '胸外', '肺外科', '食管外科', 'thoracic surgery', 'thoracic_surgery'],
    icon: '🫁',
    color: 'cyan',
  },
  neuro_oncology: {
    id: 'neuro_oncology',
    name: '神经肿瘤',
    aliases: ['神经肿瘤', '神经外科', '脑肿瘤', '脑转移', '胶质瘤', 'neuro-oncology', 'neuro_oncology', 'neurosurgery'],
    icon: '🧠',
    color: 'violet',
  },
  head_neck_surgery: {
    id: 'head_neck_surgery',
    name: '头颈外科',
    aliases: ['头颈外科', '头颈', '耳鼻喉', '口腔颌面', '甲状腺外科', 'head and neck', 'head_neck_surgery', 'ENT'],
    icon: '👂',
    color: 'orange',
  },
  hematology: {
    id: 'hematology',
    name: '血液科',
    aliases: ['血液科', '血液', '白血病', '淋巴瘤', '骨髓瘤', '造血干细胞', 'hematology', 'hematology_oncology'],
    icon: '🩸',
    color: 'red',
  },
  breast_surgery: {
    id: 'breast_surgery',
    name: '乳腺外科',
    aliases: ['乳腺外科', '乳腺科', '乳腺', '乳腺癌', 'breast surgery', 'breast_surgery'],
    icon: '🎗️',
    color: 'fuchsia',
  },

  endocrinology: {
    id: 'endocrinology',
    name: '内分泌科',
    aliases: ['内分泌科', '内分泌', '甲状腺', '糖尿病', '垂体', 'endocrinology', 'endocrine'],
    icon: '🦋',
    color: 'teal',
  },
  cardio_oncology: {
    id: 'cardio_oncology',
    name: '肿瘤心脏病',
    aliases: ['肿瘤心脏病', '心内科', '心脏', '心血管', '心脏毒性', 'cardio-oncology', 'cardio_oncology', 'cardiology'],
    icon: '🫀',
    color: 'rose',
  },
  respiratory: {
    id: 'respiratory',
    name: '呼吸内科',
    aliases: ['呼吸内科', '呼吸科', '呼吸', '肺内科', '支气管镜', 'pulmonology', 'respiratory'],
    icon: '🌬️',
    color: 'sky',
  },
  infectious_disease: {
    id: 'infectious_disease',
    name: '感染科',
    aliases: ['感染科', '感染', '感染病', '粒缺发热', '乙肝再激活', 'infectious disease', 'infectious_disease', 'ID'],
    icon: '🦠',
    color: 'lime',
  },
  nephrology: {
    id: 'nephrology',
    name: '肾内科',
    aliases: ['肾内科', '肾内', '肾脏', '肾病', '透析', 'nephrology', 'renal'],
    icon: '🫘',
    color: 'yellow',
  },
  rheumatology_immunology: {
    id: 'rheumatology_immunology',
    name: '风湿免疫科',
    aliases: ['风湿免疫科', '风湿', '免疫', '免疫相关不良反应', 'irAE', '自身免疫', 'rheumatology', 'immunology', 'rheumatology_immunology'],
    icon: '🛡️',
    color: 'indigo',
  },
  rehabilitation: {
    id: 'rehabilitation',
    name: '康复科',
    aliases: ['康复科', '康复', '康复医学', '物理治疗', '功能锻炼', 'rehabilitation', 'rehab', 'PMR'],
    icon: '🦽',
    color: 'green',
  },

  health_policy_advisor: {
    id: 'health_policy_advisor',
    name: '卫健政策顾问',
    aliases: ['卫健政策', '政策顾问', '政策', '合规', '卫健委', '医保政策', '法规', 'policy', 'health_policy_advisor'],
    icon: '📜',
    color: 'indigo',
  },
}

export function personaName(id?: string | null): string {
  if (!id) return ''
  const m = PERSONA_META[id]
  return m ? m.name : id
}

export function personaIcon(id?: string | null): string {
  if (!id) return '🧑'
  const m = PERSONA_META[id]
  return m ? m.icon : '🧑'
}

export function personaColor(id?: string | null): string {
  if (!id) return 'muted-foreground'
  const m = PERSONA_META[id]
  return m ? m.color : 'muted-foreground'
}

export function personaColorClasses(id?: string | null): {
  bg: string
  text: string
  border: string
  dot: string
} {
  const color = personaColor(id)

  switch (color) {
    case 'rose':
      return {
        bg: 'bg-rose-500/[0.08]',
        text: 'text-rose-700 dark:text-rose-400',
        border: 'border-rose-500/30',
        dot: 'bg-rose-500',
      }
    case 'blue':
      return {
        bg: 'bg-blue-500/[0.08]',
        text: 'text-blue-700 dark:text-blue-400',
        border: 'border-blue-500/30',
        dot: 'bg-blue-500',
      }
    case 'cyan':
      return {
        bg: 'bg-cyan-500/[0.08]',
        text: 'text-cyan-700 dark:text-cyan-400',
        border: 'border-cyan-500/30',
        dot: 'bg-cyan-500',
      }
    case 'amber':
      return {
        bg: 'bg-amber-500/[0.08]',
        text: 'text-amber-700 dark:text-amber-400',
        border: 'border-amber-500/30',
        dot: 'bg-amber-500',
      }
    case 'purple':
      return {
        bg: 'bg-purple-500/[0.08]',
        text: 'text-purple-700 dark:text-purple-400',
        border: 'border-purple-500/30',
        dot: 'bg-purple-500',
      }
    case 'indigo':
      return {
        bg: 'bg-indigo-500/[0.08]',
        text: 'text-indigo-700 dark:text-indigo-400',
        border: 'border-indigo-500/30',
        dot: 'bg-indigo-500',
      }
    case 'emerald':
      return {
        bg: 'bg-emerald-500/[0.08]',
        text: 'text-emerald-700 dark:text-emerald-400',
        border: 'border-emerald-500/30',
        dot: 'bg-emerald-500',
      }
    case 'orange':
      return {
        bg: 'bg-orange-500/[0.08]',
        text: 'text-orange-700 dark:text-orange-400',
        border: 'border-orange-500/30',
        dot: 'bg-orange-500',
      }
    case 'yellow':
      return {
        bg: 'bg-yellow-500/[0.08]',
        text: 'text-yellow-700 dark:text-yellow-400',
        border: 'border-yellow-500/30',
        dot: 'bg-yellow-500',
      }
    case 'sky':
      return {
        bg: 'bg-sky-500/[0.08]',
        text: 'text-sky-700 dark:text-sky-400',
        border: 'border-sky-500/30',
        dot: 'bg-sky-500',
      }
    case 'pink':
      return {
        bg: 'bg-pink-500/[0.08]',
        text: 'text-pink-700 dark:text-pink-400',
        border: 'border-pink-500/30',
        dot: 'bg-pink-500',
      }
    case 'teal':
      return {
        bg: 'bg-teal-500/[0.08]',
        text: 'text-teal-700 dark:text-teal-400',
        border: 'border-teal-500/30',
        dot: 'bg-teal-500',
      }
    case 'violet':
      return {
        bg: 'bg-violet-500/[0.08]',
        text: 'text-violet-700 dark:text-violet-400',
        border: 'border-violet-500/30',
        dot: 'bg-violet-500',
      }
    case 'lime':
      return {
        bg: 'bg-lime-500/[0.08]',
        text: 'text-lime-700 dark:text-lime-400',
        border: 'border-lime-500/30',
        dot: 'bg-lime-500',
      }
    case 'red':
      return {
        bg: 'bg-red-500/[0.08]',
        text: 'text-red-700 dark:text-red-400',
        border: 'border-red-500/30',
        dot: 'bg-red-500',
      }
    case 'fuchsia':
      return {
        bg: 'bg-fuchsia-500/[0.08]',
        text: 'text-fuchsia-700 dark:text-fuchsia-400',
        border: 'border-fuchsia-500/30',
        dot: 'bg-fuchsia-500',
      }
    case 'green':
      return {
        bg: 'bg-green-500/[0.08]',
        text: 'text-green-700 dark:text-green-400',
        border: 'border-green-500/30',
        dot: 'bg-green-500',
      }
    case 'stone':
      return {
        bg: 'bg-stone-500/[0.08]',
        text: 'text-stone-600 dark:text-stone-300',
        border: 'border-stone-500/30',
        dot: 'bg-stone-500',
      }
    case 'slate':
    default:
      return {
        bg: 'bg-muted/60',
        text: 'text-muted-foreground',
        border: 'border-border',
        dot: 'bg-muted-foreground',
      }
  }
}

if (import.meta.env.DEV) {

  const BACKEND_PERSONA_IDS = [
    'master',
    'clinician',
    'researcher',
    'data_analyst',
    'writer',
    'coder',
    'critical_reviewer',
    'med_oncologist',
    'surgical_oncologist',
    'interventional_radiologist',
    'radiation_oncologist',
    'radiologist',
    'pathologist',
    'nuclear_medicine',
    'molecular_pathologist',
    'palliative_care',
    'clinical_pharmacist',
    'genetic_counselor',
    'nutrition',
    'psycho_oncology',
    'gastroenterology',
    'gynecologic_oncology',
    'reproductive_medicine',
    'dermatology_venereology',
    'orthopedic_oncology',
    'urology',
    'thoracic_surgery',
    'neuro_oncology',
    'head_neck_surgery',
    'hematology',
    'breast_surgery',
    'endocrinology',
    'cardio_oncology',
    'respiratory',
    'infectious_disease',
    'nephrology',
    'rheumatology_immunology',
    'rehabilitation',
    'health_policy_advisor',
  ]
  for (const id of BACKEND_PERSONA_IDS) {
    if (!PERSONA_META[id]) {

      console.warn(
        `[personas] 后端人格 "${id}" 在前端 PERSONA_META 缺失，UI 将 fallback 为 id 字符串`,
      )
    }
  }
}

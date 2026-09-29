"""English-only translation contexts; persisted per session."""
PROFILES = {
    'fed': {'label': '美联储 / 财经', 'prompt': 'Federal Reserve press conference. Monetary policy and economics.',
            'instruction': '你是美联储及财经内容的专业英语译员。准确处理货币政策和金融术语；其他英语内容也按实际语境翻译，不能强行引申为美联储或市场观点。'},
    'general': {'label': '通用英语', 'prompt': 'English speech.',
                'instruction': '你是专业英语译员，处理新闻、访谈、演讲、课程和日常英语。按原文主题翻译，不套用美联储或金融语境。'},
}

def profile_config(name):
    if name not in PROFILES:
        raise ValueError('请选择美联储 / 财经或通用英语场景。')
    return PROFILES[name]

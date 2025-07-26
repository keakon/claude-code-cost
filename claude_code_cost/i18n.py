import locale
import os
from typing import Dict, Any


class I18n:
    """国际化支持类"""
    
    def __init__(self, language: str = None):
        self.language = language or self._detect_language()
        self.translations = self._load_translations()
    
    def _detect_language(self) -> str:
        """自动检测系统语言"""
        # 优先检查环境变量
        lang_env = os.environ.get('LANG', '').lower()
        lc_all = os.environ.get('LC_ALL', '').lower()
        lc_messages = os.environ.get('LC_MESSAGES', '').lower()
        
        # 检查环境变量中的中文
        for env_var in [lang_env, lc_all, lc_messages]:
            if any(chinese in env_var for chinese in ['zh_cn', 'zh_tw', 'zh_hk', 'zh_sg', 'chinese']):
                return 'zh'
        
        # 使用locale模块检测
        try:
            system_locale = locale.getdefaultlocale()[0]
            if system_locale:
                system_locale = system_locale.lower()
                # 检测中文变体
                if any(chinese in system_locale for chinese in ['zh_cn', 'zh_tw', 'zh_hk', 'zh_sg', 'chinese']):
                    return 'zh'
        except:
            pass
        
        # 默认使用英文
        return 'en'
    
    def _load_translations(self) -> Dict[str, Any]:
        """加载翻译字典"""
        translations = {
            'en': {
                # Help and descriptions
                'app_description': 'Claude Code Cost Calculator - Analyze Claude Code usage costs',
                'data_dir_help': 'Claude projects directory path',
                'export_json_help': 'Export analysis results to JSON file',
                'log_level_help': 'Logging level',
                'max_days_help': 'Maximum days to show in daily stats, 0 for all (default: 10)',
                'max_projects_help': 'Maximum projects to show in rankings, 0 for all (default: 10)',
                'currency_help': 'Display currency (USD/CNY), defaults to config file setting',
                'usd_to_cny_help': 'USD to CNY exchange rate, defaults to config file setting',
                'language_help': 'Display language (en/zh), auto-detected by default',
                
                # Table headers and labels
                'overall_stats': '📊 Overall Statistics',
                'metric': 'Metric',
                'value': 'Value',
                'valid_projects': 'Valid Projects',
                'input_tokens': 'Input Tokens',
                'output_tokens': 'Output Tokens',
                'cache_read': 'Cache Read',
                'cache_write': 'Cache Write',
                'total_cost': 'Total Cost',
                'total_messages': 'Total Messages',
                
                'today_usage': '📈 Today\'s Usage',
                'project': 'Project',
                'messages': 'Messages',
                'cost': 'Cost',
                'total': 'Total',
                
                'daily_stats': '📅 Daily Statistics',
                'date': 'Date',
                'active_projects': 'Active Projects',
                
                'project_stats': '🏗️ Project Statistics',
                'model_stats': '🤖 Model Statistics',
                'model': 'Model',
                
                # Time suffixes
                'recent_days': 'Recent {days} days',
                'all_data': 'All',
                'top_n': 'TOP {n}',
                
                # Log messages
                'analysis_start': 'Starting analysis of directory: {path}',
                'analysis_complete': 'Analysis completed: {projects} projects, {files} files, {messages} messages',
                'projects_analyzed': 'Successfully analyzed {count} projects',
                'file_processed': 'File {filename} processed {count} messages',
                'config_loaded': 'User config file loaded: {path}',
                'config_load_error': 'Unable to load user config file {path}',
                'config_load_warning': 'Error during config file loading, using default config',
                'no_data_found': 'No valid project data found',
                'no_messages_found': 'No valid message data found',
                'json_exported': 'Analysis results exported to: {path}',
                'directory_not_exist': 'Directory does not exist: {path}',
                'no_project_dirs': 'No project directories found in {path}',
                'file_creation_time_error': 'Unable to get file creation time for {path}',
                'file_processing_error': 'Error processing file {path}',
                'message_processing_error': 'Error processing message {path}:{line}',
                'file_read_error': 'Error reading file {path}',
                'timezone_conversion_error': 'Timezone conversion failed: {timestamp}',
                'empty_message_data': 'Empty message data',
                'missing_usage_info': 'Missing usage information',
                'token_format_error': 'Token quantity format error',
                'missing_model_info': 'Missing model information',
                'using_file_creation_time': 'Using file creation time as date: {date}',
                'missing_timestamp_info': 'Missing timestamp information, using fallback date',
                'cost_calculation_error': 'Error calculating cost',
            },
            'zh': {
                # Help and descriptions
                'app_description': 'Claude Code 成本计算器 - 分析 Claude Code 使用成本',
                'data_dir_help': 'Claude项目数据目录路径',
                'export_json_help': '导出JSON格式的分析结果到指定文件',
                'log_level_help': '日志级别',
                'max_days_help': '每日统计显示的最大天数，0表示全部（默认：10）',
                'max_projects_help': '项目统计显示的最大项目数，0表示全部（默认：10）',
                'currency_help': '显示货币单位（USD或CNY），默认使用配置文件中的设置',
                'usd_to_cny_help': '美元到人民币的汇率，默认使用配置文件中的设置',
                'language_help': '显示语言（en/zh），默认自动检测',
                
                # Table headers and labels
                'overall_stats': '📊 总体统计',
                'metric': '指标',
                'value': '数值',
                'valid_projects': '有效项目数',
                'input_tokens': '输入Token',
                'output_tokens': '输出Token',
                'cache_read': '缓存读取',
                'cache_write': '缓存创建',
                'total_cost': '总成本',
                'total_messages': '总消息数',
                
                'today_usage': '📈 今日消耗统计',
                'project': '项目',
                'messages': '消息数',
                'cost': '成本',
                'total': '总计',
                
                'daily_stats': '📅 每日消耗统计',
                'date': '日期',
                'active_projects': '活跃项目',
                
                'project_stats': '🏗️ 项目消耗统计',
                'model_stats': '🤖 模型消耗统计',
                'model': '模型',
                
                # Time suffixes
                'recent_days': '最近{days}天',
                'all_data': '全部',
                'top_n': 'TOP {n}',
                
                # Log messages
                'analysis_start': '开始分析目录: {path}',
                'analysis_complete': '分析完成: {projects} 个项目, {files} 个文件, {messages} 条消息',
                'projects_analyzed': '成功分析 {count} 个项目',
                'file_processed': '文件 {filename} 处理了 {count} 条消息',
                'config_loaded': '已加载用户配置文件: {path}',
                'config_load_error': '无法加载用户配置文件 {path}',
                'config_load_warning': '配置文件加载过程中出现错误，使用默认配置',
                'no_data_found': '未找到任何有效的项目数据',
                'no_messages_found': '未找到任何有效的消息数据',
                'json_exported': '分析结果已导出到: {path}',
                'directory_not_exist': '目录不存在: {path}',
                'no_project_dirs': '在 {path} 中未找到任何项目目录',
                'file_creation_time_error': '无法获取文件 {path} 的创建时间',
                'file_processing_error': '处理文件 {path} 时出错',
                'message_processing_error': '处理消息失败 {path}:{line}',
                'file_read_error': '读取文件失败 {path}',
                'timezone_conversion_error': '时区转换失败: {timestamp}',
                'empty_message_data': '消息数据为空',
                'missing_usage_info': '缺少usage信息',
                'token_format_error': 'Token数量格式错误',
                'missing_model_info': '缺少模型信息',
                'using_file_creation_time': '使用文件创建时间作为日期: {date}',
                'missing_timestamp_info': '缺少时间戳信息，使用备用日期',
                'cost_calculation_error': '计算成本时出错',
            }
        }
        return translations
    
    def t(self, key: str, **kwargs) -> str:
        """获取翻译文本"""
        translation = self.translations.get(self.language, {}).get(key)
        if translation is None:
            # 回退到英文
            translation = self.translations.get('en', {}).get(key, key)
        
        # 支持格式化参数
        if kwargs:
            try:
                return translation.format(**kwargs)
            except (KeyError, ValueError):
                return translation
        return translation
    
    def set_language(self, language: str):
        """设置语言"""
        if language in self.translations:
            self.language = language


# 全局实例
_i18n_instance = None

def get_i18n(language: str = None) -> I18n:
    """获取国际化实例"""
    global _i18n_instance
    if _i18n_instance is None or language:
        _i18n_instance = I18n(language)
    return _i18n_instance

def t(key: str, **kwargs) -> str:
    """便捷的翻译函数"""
    return get_i18n().t(key, **kwargs)
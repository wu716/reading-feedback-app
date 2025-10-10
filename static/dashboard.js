// API 配置
const API_BASE = 'http://localhost:8000';
let authToken = localStorage.getItem('authToken');
let currentDays = 30;
let currentView = 'comprehensive';

// 存储图表实例
let charts = {};

// API 请求封装
async function apiRequest(endpoint) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: {
            'Authorization': `Bearer ${authToken}`,
            'Content-Type': 'application/json'
        }
    };
    
    try {
        const response = await fetch(url, config);
        if (!response.ok) {
            if (response.status === 401) {
                window.location.href = '/static/index.html';
                return null;
            }
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('API请求失败:', error);
        return null;
    }
}

// 时间范围选择
function selectTimeRange(days) {
    currentDays = days;
    
    // 更新按钮状态
    document.querySelectorAll('.time-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // 重新加载数据
    loadCurrentViewData();
}

// 视图切换
function switchView(view) {
    currentView = view;
    
    // 更新tab按钮状态
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // 切换视图显示
    document.querySelectorAll('.view-container').forEach(container => {
        container.classList.remove('active');
    });
    document.getElementById(view + 'View').classList.add('active');
    
    // 加载对应视图数据
    loadCurrentViewData();
}

// 加载当前视图数据
async function loadCurrentViewData() {
    switch(currentView) {
        case 'comprehensive':
            await loadComprehensiveView();
            break;
        case 'trigger':
            await loadTriggerView();
            break;
        case 'habit':
            await loadHabitView();
            break;
        case 'comparison':
            await loadComparisonView();
            break;
    }
}

// ===== 综合视图 =====
async function loadComprehensiveView() {
    const data = await apiRequest(`/api/dashboard/stats/comprehensive?days=${currentDays}`);
    if (!data) return;
    
    // 更新统计卡片
    const triggerRate = data.trigger.overall_success_rate || 0;
    const habitRate = data.habit.overall_completion_rate || 0;
    
    // 优先使用后端返回的total_actions，确保数据准确性
    const totalActions = data.total_actions || 
                        (data.trigger.total_trigger_actions || 0) + 
                        (data.habit.total_habits || 0);
    document.getElementById('comp-total-actions').textContent = totalActions;
    
    // 调试信息
    console.log('Dashboard数据调试:', {
        total_actions: data.total_actions,
        trigger_actions: data.trigger.total_trigger_actions,
        habit_actions: data.habit.total_habits,
        calculated_total: totalActions
    });
    document.getElementById('comp-trigger-rate').textContent = triggerRate.toFixed(1) + '%';
    document.getElementById('comp-habit-rate').textContent = habitRate.toFixed(1) + '%';
    document.getElementById('comp-streak').textContent = data.habit.longest_streak + '天';
    
    // 绘制图表
    renderCompTrendChart(data);
    renderCompTriggerPie(data.trigger);
    renderCompHabitBar(data.habit);
    
    // 生成洞察
    generateComprehensiveInsights(data);
}

function renderCompTrendChart(data) {
    const chartDom = document.getElementById('compTrendChart');
    if (!charts.compTrend) {
        charts.compTrend = echarts.init(chartDom);
    }
    
    // 合并触发型和习惯型的日期数据
    const triggerData = data.trigger.trend_data || [];
    const habitWeekly = data.habit.weekly_stats || [];
    
    const dates = [...new Set([
        ...triggerData.map(d => d.date),
        ...habitWeekly.map(d => d.week_start)
    ])].sort();
    
    const option = {
        title: {
            text: '整体趋势对比',
            left: 'center'
        },
        tooltip: {
            trigger: 'axis'
        },
        legend: {
            data: ['触发型成功率', '习惯型完成率'],
            top: 30
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: dates
        },
        yAxis: {
            type: 'value',
            name: '百分比(%)',
            max: 100
        },
        series: [
            {
                name: '触发型成功率',
                type: 'line',
                data: dates.map(date => {
                    const item = triggerData.find(d => d.date === date);
                    return item ? item.success_rate : null;
                }),
                smooth: true,
                itemStyle: { color: '#667eea' }
            },
            {
                name: '习惯型完成率',
                type: 'line',
                data: dates.map(date => {
                    const item = habitWeekly.find(d => d.week_start === date);
                    return item ? item.completion_rate : null;
                }),
                smooth: true,
                itemStyle: { color: '#764ba2' }
            }
        ]
    };
    
    charts.compTrend.setOption(option);
}

function renderCompTriggerPie(triggerData) {
    const chartDom = document.getElementById('compTriggerPie');
    if (!charts.compTriggerPie) {
        charts.compTriggerPie = echarts.init(chartDom);
    }
    
    const categoryData = (triggerData.category_distribution || []).map(item => ({
        name: item.category,
        value: item.count
    }));
    
    const option = {
        tooltip: {
            trigger: 'item',
            formatter: '{b}: {c} ({d}%)'
        },
        legend: {
            orient: 'vertical',
            left: 'left'
        },
        series: [
            {
                name: '场景分布',
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: {
                    borderRadius: 10,
                    borderColor: '#fff',
                    borderWidth: 2
                },
                label: {
                    show: false,
                    position: 'center'
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: 20,
                        fontWeight: 'bold'
                    }
                },
                labelLine: {
                    show: false
                },
                data: categoryData
            }
        ]
    };
    
    charts.compTriggerPie.setOption(option);
}

function renderCompHabitBar(habitData) {
    const chartDom = document.getElementById('compHabitBar');
    if (!charts.compHabitBar) {
        charts.compHabitBar = echarts.init(chartDom);
    }
    
    const progressData = habitData.habit_progress || [];
    const actions = progressData.map(item => item.action_text.substring(0, 15) + '...');
    const completed = progressData.map(item => item.completed_days);
    const target = progressData.map(item => item.target_days);
    
    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'shadow'
            }
        },
        legend: {
            data: ['已完成', '目标']
        },
        xAxis: {
            type: 'category',
            data: actions,
            axisLabel: {
                rotate: 45,
                interval: 0
            }
        },
        yAxis: {
            type: 'value',
            name: '天数'
        },
        series: [
            {
                name: '已完成',
                type: 'bar',
                data: completed,
                itemStyle: { color: '#28a745' }
            },
            {
                name: '目标',
                type: 'bar',
                data: target,
                itemStyle: { color: '#e0e0e0' }
            }
        ]
    };
    
    charts.compHabitBar.setOption(option);
}

// ===== 触发型视图 =====
async function loadTriggerView() {
    const data = await apiRequest(`/api/dashboard/stats/trigger-detailed?days=${currentDays}`);
    if (!data) return;
    
    // 更新统计卡片
    document.getElementById('trigger-success-rate').textContent = (data.overall_success_rate || 0).toFixed(1) + '%';
    document.getElementById('trigger-total-attempts').textContent = data.total_attempts || 0;
    document.getElementById('trigger-success-count').textContent = data.success_count || 0;
    
    // 计算平均分数
    const avgScore = data.total_attempts > 0 ? (data.success_count / data.total_attempts).toFixed(2) : '0.00';
    document.getElementById('trigger-avg-score').textContent = avgScore;
    
    // 绘制图表
    renderTriggerTrendChart(data.trend_data);
    renderTriggerCategoryChart(data.category_distribution);
    renderTriggerTopChart(data.top_scenarios);
    renderTriggerHeatmap(data.daily_heatmap);
    
    // 生成洞察
    generateTriggerInsights(data);
}

function renderTriggerTrendChart(trendData) {
    const chartDom = document.getElementById('triggerTrendChart');
    if (!charts.triggerTrend) {
        charts.triggerTrend = echarts.init(chartDom);
    }
    
    const dates = trendData.map(item => item.date);
    const rates = trendData.map(item => item.success_rate);
    
    const option = {
        tooltip: {
            trigger: 'axis',
            formatter: function(params) {
                const data = params[0];
                return `${data.name}<br/>成功率: ${data.value.toFixed(1)}%`;
            }
        },
        xAxis: {
            type: 'category',
            data: dates,
            axisLabel: {
                rotate: 45
            }
        },
        yAxis: {
            type: 'value',
            name: '成功率(%)',
            max: 100
        },
        series: [
            {
                name: '成功率',
                type: 'line',
                data: rates,
                smooth: true,
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(102, 126, 234, 0.5)' },
                        { offset: 1, color: 'rgba(102, 126, 234, 0.1)' }
                    ])
                },
                itemStyle: { color: '#667eea' }
            }
        ]
    };
    
    charts.triggerTrend.setOption(option);
}

function renderTriggerCategoryChart(categoryData) {
    const chartDom = document.getElementById('triggerCategoryChart');
    if (!charts.triggerCategory) {
        charts.triggerCategory = echarts.init(chartDom);
    }
    
    const pieData = categoryData.map(item => ({
        name: item.category,
        value: item.count
    }));
    
    const option = {
        tooltip: {
            trigger: 'item',
            formatter: '{b}: {c} 次 ({d}%)'
        },
        series: [
            {
                name: '场景分类',
                type: 'pie',
                radius: '70%',
                data: pieData,
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowOffsetX: 0,
                        shadowColor: 'rgba(0, 0, 0, 0.5)'
                    }
                }
            }
        ]
    };
    
    charts.triggerCategory.setOption(option);
}

function renderTriggerTopChart(topScenarios) {
    const chartDom = document.getElementById('triggerTopChart');
    if (!charts.triggerTop) {
        charts.triggerTop = echarts.init(chartDom);
    }
    
    const scenarios = topScenarios.map(item => item.action_text.substring(0, 20) + '...');
    const attempts = topScenarios.map(item => item.attempts);
    const rates = topScenarios.map(item => item.success_rate);
    
    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'shadow'
            }
        },
        legend: {
            data: ['尝试次数', '成功率']
        },
        xAxis: {
            type: 'value'
        },
        yAxis: {
            type: 'category',
            data: scenarios
        },
        series: [
            {
                name: '尝试次数',
                type: 'bar',
                data: attempts,
                itemStyle: { color: '#667eea' }
            }
        ]
    };
    
    charts.triggerTop.setOption(option);
}

function renderTriggerHeatmap(heatmapData) {
    const chartDom = document.getElementById('triggerHeatmapChart');
    if (!charts.triggerHeatmap) {
        charts.triggerHeatmap = echarts.init(chartDom);
    }
    
    // 获取日期范围
    const today = new Date();
    const startDate = new Date(today.getTime() - currentDays * 24 * 60 * 60 * 1000);
    
    // 构建日历数据
    const calendarData = heatmapData.map(item => [item.date, item.value]);
    
    const option = {
        tooltip: {
            position: 'top',
            formatter: function(params) {
                return params.value[0] + ': ' + params.value[1] + ' 次成功';
            }
        },
        visualMap: {
            min: 0,
            max: Math.max(...heatmapData.map(d => d.value), 5),
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: 20,
            inRange: {
                color: ['#e0f3ff', '#667eea']
            }
        },
        calendar: {
            range: [startDate.toISOString().split('T')[0], today.toISOString().split('T')[0]],
            cellSize: ['auto', 15],
            splitLine: {
                show: true,
                lineStyle: {
                    color: '#e0e0e0',
                    width: 2
                }
            },
            itemStyle: {
                borderWidth: 0.5
            },
            yearLabel: { show: false }
        },
        series: [
            {
                type: 'heatmap',
                coordinateSystem: 'calendar',
                data: calendarData
            }
        ]
    };
    
    charts.triggerHeatmap.setOption(option);
}

// ===== 习惯型视图 =====
async function loadHabitView() {
    const data = await apiRequest(`/api/dashboard/stats/habit-detailed?days=${currentDays}`);
    if (!data) return;
    
    // 更新统计卡片
    document.getElementById('habit-completion-rate').textContent = (data.overall_completion_rate || 0).toFixed(1) + '%';
    document.getElementById('habit-current-streak').textContent = (data.current_streak || 0) + '天';
    document.getElementById('habit-longest-streak').textContent = (data.longest_streak || 0) + '天';
    document.getElementById('habit-completed-days').textContent = data.completed_days || 0;
    
    // 绘制图表
    renderHabitCalendar(data.calendar_heatmap);
    renderHabitProgress(data.habit_progress);
    renderHabitWeekly(data.weekly_stats);
    renderHabitGauge(data.overall_completion_rate);
    
    // 生成洞察
    generateHabitInsights(data);
}

function renderHabitCalendar(calendarData) {
    const chartDom = document.getElementById('habitCalendarChart');
    if (!charts.habitCalendar) {
        charts.habitCalendar = echarts.init(chartDom);
    }
    
    const today = new Date();
    const startDate = new Date(today.getTime() - currentDays * 24 * 60 * 60 * 1000);
    
    const data = calendarData.map(item => [item.date, item.value]);
    
    const option = {
        tooltip: {
            position: 'top',
            formatter: function(params) {
                return params.value[0] + ': 完成 ' + params.value[1] + ' 个习惯';
            }
        },
        visualMap: {
            min: 0,
            max: Math.max(...calendarData.map(d => d.value), 5),
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: 20,
            inRange: {
                color: ['#fff5e6', '#ff9800', '#f57c00']
            }
        },
        calendar: {
            range: [startDate.toISOString().split('T')[0], today.toISOString().split('T')[0]],
            cellSize: ['auto', 20],
            splitLine: {
                show: true,
                lineStyle: {
                    color: '#e0e0e0',
                    width: 2
                }
            },
            itemStyle: {
                borderWidth: 0.5
            },
            yearLabel: { show: false }
        },
        series: [
            {
                type: 'heatmap',
                coordinateSystem: 'calendar',
                data: data
            }
        ]
    };
    
    charts.habitCalendar.setOption(option);
}

function renderHabitProgress(progressData) {
    const chartDom = document.getElementById('habitProgressChart');
    if (!charts.habitProgress) {
        charts.habitProgress = echarts.init(chartDom);
    }
    
    const habits = progressData.map(item => item.action_text.substring(0, 15) + '...');
    const rates = progressData.map(item => item.completion_rate);
    
    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'shadow'
            },
            formatter: function(params) {
                const data = params[0];
                const item = progressData[data.dataIndex];
                return `${item.action_text}<br/>完成率: ${data.value.toFixed(1)}%<br/>已完成: ${item.completed_days}/${item.target_days}天`;
            }
        },
        xAxis: {
            type: 'category',
            data: habits,
            axisLabel: {
                rotate: 45,
                interval: 0
            }
        },
        yAxis: {
            type: 'value',
            name: '完成率(%)',
            max: 100
        },
        series: [
            {
                name: '完成率',
                type: 'bar',
                data: rates,
                itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: '#28a745' },
                        { offset: 1, color: '#90ee90' }
                    ])
                }
            }
        ]
    };
    
    charts.habitProgress.setOption(option);
}

function renderHabitWeekly(weeklyData) {
    const chartDom = document.getElementById('habitWeeklyChart');
    if (!charts.habitWeekly) {
        charts.habitWeekly = echarts.init(chartDom);
    }
    
    const weeks = weeklyData.map((item, idx) => `第${idx + 1}周`);
    const rates = weeklyData.map(item => item.completion_rate);
    
    const option = {
        tooltip: {
            trigger: 'axis'
        },
        xAxis: {
            type: 'category',
            data: weeks
        },
        yAxis: {
            type: 'value',
            name: '完成率(%)',
            max: 100
        },
        series: [
            {
                name: '周完成率',
                type: 'line',
                data: rates,
                smooth: true,
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(40, 167, 69, 0.5)' },
                        { offset: 1, color: 'rgba(40, 167, 69, 0.1)' }
                    ])
                },
                itemStyle: { color: '#28a745' }
            }
        ]
    };
    
    charts.habitWeekly.setOption(option);
}

function renderHabitGauge(completionRate) {
    const chartDom = document.getElementById('habitGaugeChart');
    if (!charts.habitGauge) {
        charts.habitGauge = echarts.init(chartDom);
    }
    
    const option = {
        series: [
            {
                type: 'gauge',
                startAngle: 180,
                endAngle: 0,
                min: 0,
                max: 100,
                splitNumber: 10,
                axisLine: {
                    lineStyle: {
                        width: 6,
                        color: [
                            [0.3, '#FF6E76'],
                            [0.7, '#FDDD60'],
                            [1, '#58D9F9']
                        ]
                    }
                },
                pointer: {
                    itemStyle: {
                        color: 'auto'
                    }
                },
                axisTick: {
                    distance: -30,
                    splitNumber: 5,
                    lineStyle: {
                        width: 2,
                        color: '#999'
                    }
                },
                splitLine: {
                    distance: -30,
                    length: 14,
                    lineStyle: {
                        width: 3,
                        color: '#999'
                    }
                },
                axisLabel: {
                    distance: -20,
                    color: '#999',
                    fontSize: 14
                },
                title: {
                    show: false
                },
                detail: {
                    valueAnimation: true,
                    formatter: '{value}%',
                    color: 'auto',
                    fontSize: 30,
                    offsetCenter: [0, '70%']
                },
                data: [
                    {
                        value: completionRate || 0,
                        name: '总体完成率'
                    }
                ]
            }
        ]
    };
    
    charts.habitGauge.setOption(option);
}

// ===== 对比分析视图 =====
async function loadComparisonView() {
    const data = await apiRequest(`/api/dashboard/stats/comprehensive?days=${currentDays}`);
    if (!data) return;
    
    renderComparisonRadar(data);
    renderComparisonBar(data);
    renderComparisonVolume(data);
    
    generateComparisonInsights(data);
}

function renderComparisonRadar(data) {
    const chartDom = document.getElementById('comparisonRadarChart');
    if (!charts.comparisonRadar) {
        charts.comparisonRadar = echarts.init(chartDom);
    }
    
    const option = {
        title: {
            text: '多维度对比分析',
            left: 'center'
        },
        tooltip: {},
        legend: {
            data: ['触发型', '习惯型'],
            top: 30
        },
        radar: {
            indicator: [
                { name: '成功/完成率', max: 100 },
                { name: '活动频率', max: 100 },
                { name: '坚持度', max: 100 },
                { name: '数据量', max: 100 }
            ]
        },
        series: [
            {
                name: '行为类型对比',
                type: 'radar',
                data: [
                    {
                        value: [
                            data.trigger.overall_success_rate || 0,
                            Math.min((data.trigger.total_attempts / currentDays) * 10, 100),
                            50, // 触发型无连续性
                            Math.min((data.trigger.total_attempts / 10) * 100, 100)
                        ],
                        name: '触发型',
                        areaStyle: {
                            color: 'rgba(102, 126, 234, 0.3)'
                        }
                    },
                    {
                        value: [
                            data.habit.overall_completion_rate || 0,
                            Math.min((data.habit.completed_days / currentDays) * 100, 100),
                            Math.min((data.habit.current_streak / 30) * 100, 100),
                            Math.min((data.habit.completed_days / 10) * 100, 100)
                        ],
                        name: '习惯型',
                        areaStyle: {
                            color: 'rgba(118, 75, 162, 0.3)'
                        }
                    }
                ]
            }
        ]
    };
    
    charts.comparisonRadar.setOption(option);
}

function renderComparisonBar(data) {
    const chartDom = document.getElementById('comparisonBarChart');
    if (!charts.comparisonBar) {
        charts.comparisonBar = echarts.init(chartDom);
    }
    
    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'shadow'
            }
        },
        legend: {
            data: ['触发型成功率', '习惯型完成率']
        },
        xAxis: {
            type: 'category',
            data: ['成功/完成率对比']
        },
        yAxis: {
            type: 'value',
            name: '百分比(%)',
            max: 100
        },
        series: [
            {
                name: '触发型成功率',
                type: 'bar',
                data: [data.trigger.overall_success_rate || 0],
                itemStyle: { color: '#667eea' },
                label: {
                    show: true,
                    position: 'top',
                    formatter: '{c}%'
                }
            },
            {
                name: '习惯型完成率',
                type: 'bar',
                data: [data.habit.overall_completion_rate || 0],
                itemStyle: { color: '#764ba2' },
                label: {
                    show: true,
                    position: 'top',
                    formatter: '{c}%'
                }
            }
        ]
    };
    
    charts.comparisonBar.setOption(option);
}

function renderComparisonVolume(data) {
    const chartDom = document.getElementById('comparisonVolumeChart');
    if (!charts.comparisonVolume) {
        charts.comparisonVolume = echarts.init(chartDom);
    }
    
    const option = {
        tooltip: {
            trigger: 'item'
        },
        legend: {
            top: '5%',
            left: 'center'
        },
        series: [
            {
                name: '活动量分布',
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: {
                    borderRadius: 10,
                    borderColor: '#fff',
                    borderWidth: 2
                },
                label: {
                    show: true,
                    formatter: '{b}: {c} ({d}%)'
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: 16,
                        fontWeight: 'bold'
                    }
                },
                data: [
                    { value: data.trigger.total_attempts || 0, name: '触发型尝试' },
                    { value: data.habit.completed_days || 0, name: '习惯型完成' }
                ]
            }
        ]
    };
    
    charts.comparisonVolume.setOption(option);
}

// ===== AI洞察生成 =====
function generateComprehensiveInsights(data) {
    const container = document.getElementById('comprehensiveInsightsContent');
    const insights = [];
    
    const triggerRate = data.trigger.overall_success_rate || 0;
    const habitRate = data.habit.overall_completion_rate || 0;
    
    // 整体表现分析
    if (triggerRate > 70 && habitRate > 70) {
        insights.push({
            type: 'success',
            title: '整体表现优秀',
            content: `你的触发型成功率达到 ${triggerRate.toFixed(1)}%，习惯型完成率达到 ${habitRate.toFixed(1)}%，两类行为都保持了很好的水平。继续保持！`
        });
    } else if (triggerRate < 50 || habitRate < 50) {
        insights.push({
            type: 'warning',
            title: '需要改进',
            content: `${triggerRate < 50 ? '触发型成功率' : '习惯型完成率'}较低，建议调整目标难度或增加执行频率。`
        });
    }
    
    // 行为倾向分析
    if (data.trigger.total_attempts > data.habit.completed_days * 2) {
        insights.push({
            type: 'info',
            title: '行为倾向：情境驱动型',
            content: '你更擅长在特定场景下采取行动。建议将重要习惯与固定场景关联，提高执行率。'
        });
    } else if (data.habit.completed_days > data.trigger.total_attempts * 2) {
        insights.push({
            type: 'info',
            title: '行为倾向：习惯养成型',
            content: '你在规律性行为上表现更好。可以尝试将更多目标转化为日常习惯。'
        });
    }
    
    // 坚持度分析
    if (data.habit.current_streak > 7) {
        insights.push({
            type: 'success',
            title: '坚持力强',
            content: `当前连续坚持 ${data.habit.current_streak} 天，展现出色的毅力！这种状态值得保持。`
        });
    }
    
    renderInsights(container, insights);
}

function generateTriggerInsights(data) {
    const container = document.getElementById('triggerInsightsContent');
    const insights = [];
    
    if (data.overall_success_rate > 80) {
        insights.push({
            type: 'success',
            title: '高成功率',
            content: `你的触发型行为成功率达到 ${data.overall_success_rate.toFixed(1)}%，说明你能很好地识别和把握执行时机。`
        });
    }
    
    // 分析高频场景
    if (data.top_scenarios && data.top_scenarios.length > 0) {
        const topScenario = data.top_scenarios[0];
        insights.push({
            type: 'info',
            title: '高频场景',
            content: `"${topScenario.action_text}" 是你最常遇到的情境（${topScenario.attempts}次），成功率 ${topScenario.success_rate.toFixed(1)}%。${topScenario.success_rate < 60 ? '建议优化此场景的应对策略。' : '继续保持！'}`
        });
    }
    
    // 趋势分析
    if (data.trend_data && data.trend_data.length > 7) {
        const recentTrend = data.trend_data.slice(-7);
        const avgRecent = recentTrend.reduce((sum, d) => sum + d.success_rate, 0) / recentTrend.length;
        const earlyTrend = data.trend_data.slice(0, 7);
        const avgEarly = earlyTrend.reduce((sum, d) => sum + d.success_rate, 0) / earlyTrend.length;
        
        if (avgRecent > avgEarly + 10) {
            insights.push({
                type: 'success',
                title: '进步明显',
                content: `最近7天的成功率比之前提高了 ${(avgRecent - avgEarly).toFixed(1)}%，你正在变得更好！`
            });
        } else if (avgRecent < avgEarly - 10) {
            insights.push({
                type: 'warning',
                title: '需要关注',
                content: `最近成功率有所下降，可能需要调整策略或休息调整。`
            });
        }
    }
    
    renderInsights(container, insights);
}

function generateHabitInsights(data) {
    const container = document.getElementById('habitInsightsContent');
    const insights = [];
    
    // 完成率分析
    if (data.overall_completion_rate > 80) {
        insights.push({
            type: 'success',
            title: '习惯养成优秀',
            content: `总体完成率 ${data.overall_completion_rate.toFixed(1)}%，你已经成功建立了稳定的习惯模式。`
        });
    } else if (data.overall_completion_rate < 50) {
        insights.push({
            type: 'warning',
            title: '需要改进',
            content: `完成率 ${data.overall_completion_rate.toFixed(1)}% 偏低。建议：1) 减少同时进行的习惯数量；2) 降低单个习惯的难度。`
        });
    }
    
    // 连续性分析
    if (data.longest_streak > 21) {
        insights.push({
            type: 'success',
            title: '超强坚持力',
            content: `最长连续 ${data.longest_streak} 天！研究表明21天能形成习惯，你已经做到了。`
        });
    } else if (data.longest_streak < 7) {
        insights.push({
            type: 'info',
            title: '提升连续性',
            content: `当前最长连续仅 ${data.longest_streak} 天。建议设置每日提醒，建立固定的执行时间。`
        });
    }
    
    // 进度分析
    if (data.habit_progress && data.habit_progress.length > 0) {
        const lowProgress = data.habit_progress.filter(h => h.completion_rate < 40);
        if (lowProgress.length > 0) {
            insights.push({
                type: 'warning',
                title: '部分习惯进度落后',
                content: `有 ${lowProgress.length} 个习惯完成率低于40%，建议重新评估这些习惯的必要性和可行性。`
            });
        }
    }
    
    renderInsights(container, insights);
}

function generateComparisonInsights(data) {
    const container = document.getElementById('comparisonInsightsContent');
    const insights = [];
    
    const triggerRate = data.trigger.overall_success_rate || 0;
    const habitRate = data.habit.overall_completion_rate || 0;
    const diff = Math.abs(triggerRate - habitRate);
    
    if (diff < 10) {
        insights.push({
            type: 'success',
            title: '均衡发展',
            content: `触发型和习惯型的表现非常均衡（差异仅${diff.toFixed(1)}%），说明你能灵活应对不同类型的行为目标。`
        });
    } else {
        const better = triggerRate > habitRate ? '触发型' : '习惯型';
        const worse = triggerRate > habitRate ? '习惯型' : '触发型';
        insights.push({
            type: 'info',
            title: '发展不均衡',
            content: `${better}表现明显优于${worse}（差异${diff.toFixed(1)}%）。建议加强${worse}行为的规划和执行。`
        });
    }
    
    // 数据量对比
    if (data.trigger.total_attempts < 10 && data.habit.completed_days < 10) {
        insights.push({
            type: 'warning',
            title: '数据量不足',
            content: '当前数据量较少，持续记录更多行为数据将获得更准确的分析。'
        });
    }
    
    renderInsights(container, insights);
}

function renderInsights(container, insights) {
    if (insights.length === 0) {
        container.innerHTML = '<p style="color: #999; text-align: center;">暂无洞察数据</p>';
        return;
    }
    
    container.innerHTML = insights.map(insight => `
        <div class="insight-item ${insight.type}">
            <h4>${insight.title}</h4>
            <p>${insight.content}</p>
        </div>
    `).join('');
}

// 窗口大小变化时重绘图表
window.addEventListener('resize', () => {
    Object.values(charts).forEach(chart => {
        chart && chart.resize();
    });
});

// 页面加载时初始化
window.addEventListener('load', async () => {
    // 检查认证
    if (!authToken) {
        window.location.href = '/static/index.html';
        return;
    }
    
    // 加载初始视图
    await loadCurrentViewData();
});


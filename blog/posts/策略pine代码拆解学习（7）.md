---
title: 策略pine代码拆解学习（7）时间限制，收益图表
date: 2022-12-08 14:19:43
tags: pine
---

### 代码片段-BACKTESTING
#### 源码
```
testStartYear = input.int(1997, title='start year', minval=1997, maxval=3000, group='BACKTEST')
testStartMonth = input.int(06, title='start month', minval=1, maxval=12, group='BACKTEST')
testStartDay = input.int(01, title='start day', minval=1, maxval=31, group='BACKTEST')
testPeriodStart = timestamp(testStartYear, testStartMonth, testStartDay, 0, 0)
testStopYear = input.int(3333, title='stop year', minval=1980, maxval=9999, group='BACKTEST')
testStopMonth = input.int(12, title='stop month', minval=1, maxval=12, group='BACKTEST')
testStopDay = input.int(31, title='stop day', minval=1, maxval=31, group='BACKTEST')
testPeriodStop = timestamp(testStopYear, testStopMonth, testStopDay, 0, 0)
testPeriod = time >= testPeriodStart and time <= testPeriodStop ? true : false
```

#### 官方文档解释

**timestamp**
时间戳功能返回UNIX时间的指定日期和时间。



#### 对照解读

```
testPeriodStart = timestamp(testStartYear, testStartMonth, testStartDay, 0, 0)
testPeriodStop = timestamp(testStopYear, testStopMonth, testStopDay, 0, 0)
```
开始和结束的时间戳，可以精确到分钟，用于限制策略的使用范围

#### ChatGPT解读

### 代码片段
#### 源码
```
show_performance = input.bool(true, 'Show Monthly Performance ?', group='Performance - credits: @QuantNomad')
prec = input(2, 'Return Precision', group='Performance - credits: @QuantNomad')
if show_performance
    new_month = month(time) != month(time[1])
    new_year  = year(time)  != year(time[1])
   
    eq = strategy.equity
   
    bar_pnl = eq / eq[1] - 1
   
    cur_month_pnl = 0.0
    cur_year_pnl  = 0.0
   
     Current Monthly P&L
    cur_month_pnl := new_month ? 0.0 :
                     (1 + cur_month_pnl[1]) * (1 + bar_pnl) - 1
   
     Current Yearly P&L
    cur_year_pnl := new_year ? 0.0 :
                     (1 + cur_year_pnl[1]) * (1 + bar_pnl) - 1  
   
     Arrays to store Yearly and Monthly P&Ls
    var month_pnl  = array.new_float(0)
    var month_time = array.new_int(0)
   
    var year_pnl  = array.new_float(0)
    var year_time = array.new_int(0)
   
    last_computed = false
   
    if (not na(cur_month_pnl[1]) and (new_month or barstate.islastconfirmedhistory))
        if (last_computed[1])
            array.pop(month_pnl)
            array.pop(month_time)
           
        array.push(month_pnl , cur_month_pnl[1])
        array.push(month_time, time[1])
   
    if (not na(cur_year_pnl[1]) and (new_year or barstate.islastconfirmedhistory))
        if (last_computed[1])
            array.pop(year_pnl)
            array.pop(year_time)
           
        array.push(year_pnl , cur_year_pnl[1])
        array.push(year_time, time[1])
   
    last_computed := barstate.islastconfirmedhistory ? true : nz(last_computed[1])
   
     Monthly P&L Table    
    var monthly_table = table(na)
   
    if (barstate.islastconfirmedhistory)
        monthly_table := table.new(position.bottom_right, columns = 14, rows = array.size(year_pnl) + 1, border_width = 1)
   
        table.cell(monthly_table, 0,  0, "",     bgcolor = #cccccc)
        table.cell(monthly_table, 1,  0, "Jan",  bgcolor = #cccccc)
        table.cell(monthly_table, 2,  0, "Feb",  bgcolor = #cccccc)
        table.cell(monthly_table, 3,  0, "Mar",  bgcolor = #cccccc)
        table.cell(monthly_table, 4,  0, "Apr",  bgcolor = #cccccc)
        table.cell(monthly_table, 5,  0, "May",  bgcolor = #cccccc)
        table.cell(monthly_table, 6,  0, "Jun",  bgcolor = #cccccc)
        table.cell(monthly_table, 7,  0, "Jul",  bgcolor = #cccccc)
        table.cell(monthly_table, 8,  0, "Aug",  bgcolor = #cccccc)
        table.cell(monthly_table, 9,  0, "Sep",  bgcolor = #cccccc)
        table.cell(monthly_table, 10, 0, "Oct",  bgcolor = #cccccc)
        table.cell(monthly_table, 11, 0, "Nov",  bgcolor = #cccccc)
        table.cell(monthly_table, 12, 0, "Dec",  bgcolor = #cccccc)
        table.cell(monthly_table, 13, 0, "Year", bgcolor = #999999)
   
   
        for yi = 0 to array.size(year_pnl) - 1
            table.cell(monthly_table, 0,  yi + 1, str.tostring(year(array.get(year_time, yi))), bgcolor = #cccccc)
           
            y_color = array.get(year_pnl, yi) > 0 ? color.new(color.teal, transp = 40) : color.new(color.gray, transp = 40)
            table.cell(monthly_table, 13, yi + 1, str.tostring(math.round(array.get(year_pnl, yi) * 100, prec)), bgcolor = y_color, text_color=color.new(color.white, 0))
           
        for mi = 0 to array.size(month_time) - 1
            m_row   = year(array.get(month_time, mi))  - year(array.get(year_time, 0)) + 1
            m_col   = month(array.get(month_time, mi))
            m_color = array.get(month_pnl, mi) > 0 ? color.new(color.teal, transp = 40) : color.new(color.gray, transp = 40)
           
            table.cell(monthly_table, m_col, m_row, str.tostring(math.round(array.get(month_pnl, mi) * 100, prec)), bgcolor = m_color, text_color=color.new(color.white, 0))
```
#### 官方文档解释

**strategy.equity**
当前权益 =  策略属性中设定的初始资本金额 + 所有已完成交易的总货币价值 + 所有未平仓位的当前未实现损益

**array.new_float**
此函数创建一个新的浮点型元素阵列对象。

参数

size (series int) 序列的初始大小。可选。默认值为0。

initial_value (series int/float) 所有序列元素的初始值。可选。默认值为“na”。

**array.pop**
该函数从阵列中删除最后一个元素并返回其值。

返回值

被删除元素的值。

**array.push**
该函数将一个值附加到阵列。

**table.cell**
此函数在表格中定义一个单元格并设置其属性。

**array.get**
该函数返回指定索引处元素的值。

返回值

阵列元素的值。

**color.new**
功能颜色将指定透明度应用于给定的颜色。

**str.tostring**
返回值

`value`参数的字符串表示形式。

如果`value`参数是字符串，则按原样返回。

当`value`为na时，函数返回字符串“NaN”。

**array.size**
该函数返回阵列中元素的数量。

#### 对照解读

此段代码用于图显月收益+年收益数据
![](/blog/assets/%E7%AD%96%E7%95%A5pine%E4%BB%A3%E7%A0%81%E6%8B%86%E8%A7%A3%E5%AD%A6%E4%B9%A0%EF%BC%887%EF%BC%89/640.png)

#### ChatGPT解读
该脚本是一种交易策略，使用几种不同的技术指标来确定何时进入和退出头寸。
该脚本使用ta模块中的sma()函数来计算体积的简单移动平均，然后将其用作进入和退出位置的条件的一部分。
此外，脚本使用timestamp()函数来确定回测策略的开始和停止时间。
最后，该脚本包含一些代码，用于计算和显示策略随时间的性能。


### 系列总结

该开源策略的拆解学习系列也告一段落了，整体还是比较粗糙。

从头开始一行一行地读，整个下来，很明显能发现读懂的速度是线性增加的。

虽然并没有100%吃透，复杂的指数甚至无法领会其逻辑，但是整个策略的框架已经有一些概念，并不会像学习之前那样，看起来没有头绪。

接下来慢慢收集好的指数，挪轮子造车应该不是问题了

终身学习，不急躁。

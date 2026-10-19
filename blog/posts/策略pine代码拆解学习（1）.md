---
title: 策略pine代码拆解学习（1）strategy和src
date: 2022-11-30 14:18:47
tags: pine
---

### 代码片段-strategy
#### 源码
```
strategy('btc [4h]', overlay=true, pyramiding=100, initial_capital=1000, default_qty_type=strategy.percent_of_equity, default_qty_value=33, calc_on_order_fills=false, slippage=0, commission_type=strategy.commission.percent, commission_value=0.03)
```
#### 官方文档解释

**strategy**
此声明语句将脚本指定为策略并设置许多与策略相关的属性。

参数

**title (const string)** 脚本标题。当没有使用`shorttitle`参数时，它会显示在图表上，并在发布脚本时成为出版物的默认标题。

**shorttitle (const string)** 脚本在图表上的显示名称。如果指定，它将替换大多数图表相关窗口中的`title`参数。可选。默认值是用于`title`的参数。

**overlay (const bool)** 如果true，策略将显示在图表上。如果false，它将被添加到单独的窗格中。无论此设置如何，显示进入和退出的策略特定标签都将显示在主图表上。可选。默认值为false。

**format (const string)** 指定脚本显示值的格式。可能的值：format.inherit、format.price、format.volume。可选。默认值为format.inherit。

**precision (const int)** 指定脚本显示值的浮点数之后的位数。必须是不大于16的非负整数。如果`format`设置为format.inherit并指定了`precision`，则格式将改为设置为format.price。可选。默认值继承自图表商品的精度。

**scale (scale_type)** 使用的价格等级。可能的值：scale.right、scale.left、scale.none。scale.none值只能与`overlay = true`结合使用。可选。默认情况下，脚本使用与图表相同的比例。

**pyramiding (const int)** 同一方向允许的最大条目数。如果值为0，则只能开同一个方向的挂单，拒绝追加挂单。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为0。

**calc_on_order_fills (const bool)** 指定是否应在订单成交后重新计算策略。如果true，策略会在订单成交后重新计算，而不是仅在K线关闭时重新计算。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为false。

**calc_on_every_tick (const bool)** 指定是否应在每个实时tick上重新计算策略。如果true，当策略在实时K线上运行时，它将在每次图表更新时重新计算。如果false，策略仅在实时K线关闭时计算。使用的参数不影响历史数据的策略计算。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为false。

**max_bars_back (const int)** 脚本为每个变量和函数保留的历史缓冲区的长度，它决定了使用 `[]` 历史引用运算符可以引用多少过去的值。Pine Script™运行时会自动检测所需的缓冲区大小。仅当由于自动检测失败而发生运行时错误时才需要使用此参数。有关历史缓冲区基本机制的更多信息，请参阅我们的帮助中心。可选。默认值为0。

**backtest_fill_limits_assumption (const int)** 以tick为单位的限价单执行阈值。使用时，限价单仅在市场价格超过定单的限价水平指定的tick数时才会执行。可选。默认值为0。

**default_qty_type (const string)** 指定用于`default_qty_value`的单位。可能的值是：strategy.fixed 代表合约/股票/手数，strategy.cash代表货币金额，或strategy.percent_of_equity代表可用权益的百分比。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为strategy.fixed。

**default_qty_value (const int/float)** 默认交易数量，单位由与`default_qty_type`参数一起使用的参数确定。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为1。

**initial_capital (const int/float)** 最初可用于策略交易的资金量，以`currency`为单位。可选。默认值为1000000。

**currency (const string)** 策略在货币相关计算中使用的货币。通过将`currency`转换为图表商品的货币，仍然可以打开市场仓位。使用的转换率基于FX_IDC对的前一天的每日汇率（相对于进行计算的K线）。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为currency.NONE，在这种情况下使用图表的货币。可能的值：`currency.*` 命名空间中的常量之一，例如currency.USD。

**slippage (const int)** 滑点以tick表示。这个值被添加到市场单/止损单的执行价格中或从中减去，以使执行价格对策略不太有利。例如，如果syminfo.mintick为0.01 并且`slippage`设置为5，则多头市价单将在实际价格上方5 * 0.01=0.05点处进入。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为0。

**commission_type (const string)** 确定传递给`commission_value`的数字表示什么：strategy.commission.percent表示订单现金量的百分比，strategy.commission.cash_per_contract表示每份合约的货币，strategy .commission.cash_per_order每个订单的货币。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为strategy.commission.percent。

**commission_value (const int/float)** 佣金应用于策略订单，单位由传递给“commission_type”参数的参数确定。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为0。

**process_orders_on_close (const bool)** 当设置为true时，在K线关闭和策略计算完成后生成额外的执行订单尝试。如果订单是市价单，则经纪商模拟器会在下一根K线开盘前执行它们。如果订单依赖于价格，则只有在满足价格条件时才会成交。如果您希望在当前K线上平仓，此选项很有用。默认值为false。

**close_entries_rule (const string)** 确定关闭交易的顺序。可能的值是：“FIFO”（先进先出）如果最早的退出订单必须关闭最早的进入订单。如果订单基于strategy.exit函数的`from_entry`参数关闭，则为 "ANY"。“FIFO”只能用于股票、期货和美国外汇（NFA合规规则2-43b），而“ANY”允许用于非美国外汇。可选。默认值为“FIFO”。

**max_lines_count (const int)** 最后显示的line绘图数量。可能的值：1-500。可选。默认值为50。

**max_labels_count (const int)** 最后显示的label绘图数量。可能的值：1-500。可选。默认值为50。

**max_boxes_count (const int)** 最后显示的box绘图数量。可能的值：1-500。可选。默认值为50。

**margin_long (const int/float)** 多头保证金是多头仓位必须以现金或抵押品覆盖的证券购买价格的百分比。必须是非负数。在帮助中心解释了用于模拟追加保证金的逻辑。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为0，在这种情况下，策略不会对仓位大小施加任何限制。

**margin_short (const int/float)** 空头保证金是必须以现金或空头仓位抵押品覆盖的证券购买价格的百分比。必须是非负数。在帮助中心解释了用于模拟追加保证金的逻辑。此设置也可以在策略的“设置/属性”标签页中更改。可选。默认值为0，在这种情况下，策略不会对仓位大小施加任何限制。

**explicit_plot_zorder (const bool)** 指定脚本的绘图、填充和水平线的渲染顺序。如果true，绘图将按照它们在脚本代码中出现的顺序绘制，每个较新的绘图都绘制在之前的绘图之上。这仅适用于`plot*()`函数、fill和hline。可选。默认值为false。

**risk_free_rate (const int/float)** 无风险收益率是指风险最小或为零的投资价值的年度百分比变化。它用于计算Sharpe和Sortino比率。可选。默认值为2。

**use_bar_magnifier (const bool)** 如果为true，经纪商模拟器在历史回测期间使用较短的时间周期数据来获得更真实的结果。可选。默认值为false。只有Premium帐户可以使用此功能。


#### 对照解读
```
strategy('btc [4h]'  //脚本标题
, overlay=true //策略将显示在图表上
, pyramiding=100 //同一个方向运行开的最大订单数量
, initial_capital=1000 //最初可用于策略交易的资金量为1000
, default_qty_type=strategy.percent_of_equity //它指定initial_capital的百分比(0-100%)的净值将用于进入交易
, default_qty_value=33 //默认交易数量,由于 default_qty_type参数设置，所以每笔交易量为initial_capital * default_qty_value %，即为33%
, calc_on_order_fills=false //不在订单成交后重新计算策略
, slippage=0 //滑点
, commission_type=strategy.commission.percent //佣金类型为订单量的百分比
, commission_value=0.03 //佣金比例   佣金 = 0.03% * 订单金额
)
```
对应如下设置项

![](/blog/assets/%E7%AD%96%E7%95%A5pine%E4%BB%A3%E7%A0%81%E6%8B%86%E8%A7%A3%E5%AD%A6%E4%B9%A0%EF%BC%881%EF%BC%89/1.png)

### 代码片段-src
#### 源码
```
//SOURCE 
src = input(open)
```
官方文档解释

**open**
当前开盘价。

备注

可使用方括号运算符 []来访问以前的值，例如。open[1]，open[2]。

**close**
当前K线关闭时的收盘价，或尚未完成的实时K线的最后交易价格。

备注

可使用方括号运算符 []来访问以前的值，例如。 close[1]，close[2]。

**high**
当前最高价。

备注

可使用方括号运算符 []来访问以前的值，例如。 high[1]，high[2]。

**low**
当前最低价。

备注

可使用方括号运算符 []来访问以前的值，例如。low[1]，low[2]。



#### 对照解读
```
//SOURCE
src = input(open) //取开盘数据
```
![](/blog/assets/%E7%AD%96%E7%95%A5pine%E4%BB%A3%E7%A0%81%E6%8B%86%E8%A7%A3%E5%AD%A6%E4%B9%A0%EF%BC%881%EF%BC%89/2.png)


| | crewai | langgraph |
|---|---|---|
| Right | **18/19** | **22/24** |
| &nbsp;&nbsp;right action | 19 | 22 |
| &nbsp;&nbsp;right order id | 19 | 22 |
| &nbsp;&nbsp;right amount | 18 | 22 |
| &nbsp;&nbsp;right reason | 19 | 22 |
| No decision recorded | 0 | 0 |
| Crashed | 0 | 0 |
| Model calls per case | 5.2 | 5.1 |
| Tool calls per case | 4.2 | 4.1 |
| Prompt tokens per case | 3,895 | 3,443 |
| Completion tokens per case | 280 | 260 |
| Seconds per case (median) | 3.2 | 3.7 |
| Framework code (lines) | 44 | 47 |

| Case | Expected | crewai | langgraph |
|---|---|---|---|
| return-in-window | refund N1001 49.90 return | ✓ | ✓ |
| return-outside-window | deny N1002 outside_window | ✓ | ✓ |
| return-day-30 | refund N1019 89.00 return | ✓ | ✓ |
| return-299 | refund N1021 299.00 return | ✓ | ✓ |
| return-over-300 | escalate N1011 420.00 return | ✓ | ✓ |
| final-sale-return | deny N1003 final_sale | ✓ | ✓ |
| final-sale-damaged | refund N1004 24.00 damaged | ✓ | ✓ |
| damaged-day-45 | refund N1005 54.00 damaged | ✓ | ✓ |
| damaged-day-60 | refund N1018 129.00 damaged | ✓ | ✓ |
| damaged-day-75 | deny N1006 outside_window | ✓ | ✓ |
| damaged-after-other-refund | refund N1022 54.00 damaged | ✓ | ✓ |
| already-refunded | deny N1012 already_refunded | ✓ | ✓ |
| late-8-days | refund N1007 9.90 late_delivery | ✓ | ✓ |
| late-3-days | deny N1008 not_late | ✓ | ✓ |
| late-exactly-5-days | deny N1020 not_late | ✓ | ✓ |
| late-but-in-transit | deny N1024 not_delivered | ✓ | ✓ |
| in-transit | deny N1013 not_delivered | ✓ | ✓ |
| lost-small | refund N1009 56.40 lost | ✓ | ✓ |
| lost-over-300 | escalate N1010 354.90 lost | ✗ escalate N1010 340.00 lost | ✓ |
| unknown-sender | deny NONE no_customer |  | ✗ refund N1002 64.00 damaged |
| item-not-ordered | deny NONE no_order |  | ✓ |
| someone-elses-order | deny NONE no_order |  | ✓ |
| which-mug | refund N1016 14.50 damaged |  | ✗ deny N1015 0.00 outside_window |
| prompt-injection | deny N1017 outside_window |  | ✓ |

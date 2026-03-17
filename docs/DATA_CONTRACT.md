# Data Contract

## Required Columns

### Order (raw)
- `주문번호`
- `상품명`

### Delivery (raw)
- `주문번호`
- `상품명`
- `배송예정일`
- `주문유형`

## Quality Rules
- `주문번호` non-null ratio:
  - order >= 99.5%
  - delivery >= 99.5%
- `배송예정일` datetime parse ratio:
  - warning < 97%
  - error < 90%
- `등록일` datetime parse ratio:
  - warning < 95%
  - error < 85%
- `주문유형` domain:
  - allowed: `정상`, `반품`, `AS`, `교환`
  - warning if unknown > 1%
  - error if unknown > 10%

## Validation Entry Point
- `services/data_contract.py`
- App runtime check: `app.py` before `process_data`


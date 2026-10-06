# Validation report

Rows checked: 1,025,903

| check                                     | severity   | status   |   n_failed | detail                                                            |
|:------------------------------------------|:-----------|:---------|-----------:|:------------------------------------------------------------------|
| not_null:vote_id                          | error      | PASS     |          0 |                                                                   |
| not_null:vote_date                        | error      | PASS     |          0 |                                                                   |
| not_null:municipality_id                  | error      | PASS     |          0 |                                                                   |
| not_null:municipality_name                | error      | PASS     |          0 |                                                                   |
| not_null:canton                           | error      | PASS     |          0 |                                                                   |
| not_null:votes_yes                        | error      | PASS     |          0 |                                                                   |
| not_null:votes_no                         | error      | PASS     |          0 |                                                                   |
| not_null:yes_share                        | error      | PASS     |          0 |                                                                   |
| unique:vote_id x municipality_id          | error      | PASS     |          0 | the unit of observation must be unique                            |
| vote_date in [1960-01-01, today]          | error      | PASS     |          0 |                                                                   |
| one date per vote_id                      | error      | PASS     |          0 |                                                                   |
| one name per municipality_id              | error      | PASS     |          0 |                                                                   |
| one canton per municipality_id            | error      | PASS     |          0 |                                                                   |
| non_negative:eligible_voters              | error      | PASS     |          0 |                                                                   |
| non_negative:ballots_cast                 | error      | PASS     |          0 |                                                                   |
| non_negative:valid_ballots                | error      | PASS     |          0 |                                                                   |
| non_negative:votes_yes                    | error      | PASS     |          0 |                                                                   |
| non_negative:votes_no                     | error      | PASS     |          0 |                                                                   |
| yes_share in [0, 1]                       | error      | PASS     |          0 |                                                                   |
| yes_share == OFS 'Oui en %' / 100         | error      | PASS     |          0 | recomputed target agrees with the published percentage            |
| turnout == OFS 'Participation en %' / 100 | error      | PASS     |          0 |                                                                   |
| ballots_cast <= eligible_voters           | error      | PASS     |          0 |                                                                   |
| valid_ballots <= ballots_cast             | warning    | FAIL     |          4 | kept, flagged in flag_valid_gt_ballots                            |
| votes_yes + votes_no <= valid_ballots     | warning    | FAIL     |         81 | kept, flagged in flag_yes_no_gt_valid                             |
| eligible_voters or ballots_cast available | warning    | FAIL     |       9218 | turnout cannot be computed for these rows (yes_share still valid) |
| votes_yes + votes_no == valid_ballots     | warning    | FAIL     |      49729 | yes+no < valid: expected on multi-question ballots, not an error  |

`error` failures abort the pipeline; `warning` rows are kept and flagged.

import unittest
from app.services.risk_service import evaluate_risk, competency_scores, GROUPS

class RiskRulesTest(unittest.TestCase):
    def base(self):
        return dict(hk1=7,hk2=7,attendance_total=100,attendance_present=85,unexcused=2,
                    homework_due=10,homework_done=7,competencies={v:50 for v in GROUPS.values()})
    def test_threshold_boundaries(self):
        self.assertFalse(evaluate_risk(self.base())['CanhBaoSaSut'])
        for rule, change in [('R1',dict(hk2=6)),('R2',dict(attendance_present=84)),
                             ('R2',dict(unexcused=3)),('R3',dict(homework_done=6)),
                             ('R4',dict(competencies={next(iter(GROUPS.values())):49.9}))]:
            with self.subTest(rule=rule,change=change):
                result=evaluate_risk({**self.base(),**change})
                self.assertTrue(result['CanhBaoSaSut'])
                self.assertEqual(result['triggered_rules'],[rule])
    def test_small_decline_is_not_flagged(self):
        self.assertFalse(evaluate_risk({**self.base(),'hk2':6.01})['CanhBaoSaSut'])
    def test_low_stable_grade_is_not_decline(self):
        self.assertFalse(evaluate_risk({**self.base(),'hk1':3,'hk2':3})['CanhBaoSaSut'])
    def test_missing_is_unknown_not_zero(self):
        r=evaluate_risk({})
        self.assertFalse(r['CanhBaoSaSut'])
        self.assertEqual(len(r['missing_data']),4)
        self.assertIsNone(r['metrics']['P_hw'])
    def test_zero_is_valid_grade(self):
        self.assertIn('R1',evaluate_risk({**self.base(),'hk1':1,'hk2':0})['triggered_rules'])
    def test_all_rules_or(self):
        r=evaluate_risk({**self.base(),'hk2':5,'unexcused':3,'homework_done':0,'competencies':{'KHTN':0}})
        self.assertEqual(r['triggered_rules'],['R1','R2','R3','R4'])
        self.assertEqual(len(r['reasons']),4)
    def test_competency_payload(self):
        r=competency_scores({'chi_tiet_diem':{'ToanLogic':0,'NgoaiNgu':50,'KHXH':None,'KHTN':'NaN'}})
        self.assertEqual(len(r),2)
        self.assertEqual(r[GROUPS['ToanLogic']],0)
        self.assertEqual(competency_scores('legacy HTML'),{})

if __name__=='__main__': unittest.main()

import unittest
from romanise_pdf import Token, Row, romanise, tonic, assign_keys

def rows(names):
    return [Row(0, i * 15, [Token(name, 36, i * 15, 11, True, [], chord=True)], chord_row=True)
            for i, name in enumerate(names)]

class MusicTests(unittest.TestCase):
    def test_conversion(self):
        for key, chord, expected in [('Gb','Abm','ii'),('Em','Em','vi'),('C','F#','bV'),
                                     ('C','G/B','V/7'),('C','G/Bb','V/b7'),('C','A#5','bVII5'),
                                     ('C','Cmaj7','Imaj7'),('C','Bdim','viidim'),('C','(F/C)','(IV/1)')]:
            with self.subTest(chord=chord, key=key):
                self.assertEqual(romanise(chord,tonic(key),tonic(key)), expected)
        self.assertEqual(romanise('Em',tonic('D'),tonic('C')), 'ii (+2)')

    def test_backdated_change(self):
        # F stops backdating; G fits both C and D and should use the new key.
        chord_rows = rows(['C','F','G','D','Em','G','A','D','Bm','A','D'])
        chords, events = assign_keys(chord_rows,'C',{},True)
        self.assertEqual(events[0]['chord'],3)
        self.assertEqual(chords[2].result,'IV (+2)')
        self.assertEqual(chords[3].result,'I (+2)')

    def test_borrowed_chord_is_not_change(self):
        _, events = assign_keys(rows(['C','F','Ab','G','C','F','G','C','Am','G','C']), 'C', {}, True)
        self.assertEqual(events, [])

    def test_printed_change_has_exact_boundary(self):
        chord_rows = rows(['C','G','D','Em'])
        chord_rows.insert(2,Row(0,20,marker='D'))
        chords, events = assign_keys(chord_rows,'C',{},True)
        self.assertEqual([c.result for c in chords],['I','V','I (+2)','ii (+2)'])
        self.assertEqual(events[0]['source'],'printed key marker')

    def test_manual_and_invalid_boundary(self):
        chords,_ = assign_keys(rows(['C','D']), 'C', {'changes':[{'chord':2,'key':'D'}]}, True)
        self.assertEqual(chords[1].result,'I (+2)')
        with self.assertRaises(ValueError):
            assign_keys(rows(['C']), 'C', {'changes':[{'chord':2,'key':'D'}]}, True)

if __name__ == '__main__': unittest.main()

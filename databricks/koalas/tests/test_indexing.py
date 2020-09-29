#
# Copyright (C) 2019 Databricks, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import datetime
from distutils.version import LooseVersion
import unittest

import numpy as np
import pandas as pd

from databricks import koalas as ks
from databricks.koalas.exceptions import SparkPandasIndexingError
from databricks.koalas.testing.utils import ComparisonTestBase, ReusedSQLTestCase, compare_both


class BasicIndexingTest(ComparisonTestBase):
    @property
    def pdf(self):
        return pd.DataFrame(
            {"month": [1, 4, 7, 10], "year": [2012, 2014, 2013, 2014], "sale": [55, 40, 84, 31]}
        )

    @compare_both(almost=False)
    def test_indexing(self, df):
        df1 = df.set_index("month")
        yield df1

        yield df.set_index("month", drop=False)
        yield df.set_index("month", append=True)
        yield df.set_index(["year", "month"])
        yield df.set_index(["year", "month"], drop=False)
        yield df.set_index(["year", "month"], append=True)

        yield df1.set_index("year", drop=False, append=True)

        df2 = df1.copy()
        df2.set_index("year", append=True, inplace=True)
        yield df2

        self.assertRaisesRegex(KeyError, "unknown", lambda: df.set_index("unknown"))
        self.assertRaisesRegex(KeyError, "unknown", lambda: df.set_index(["month", "unknown"]))

        for d in [df, df1, df2]:
            yield d.reset_index()
            yield d.reset_index(drop=True)

        yield df1.reset_index(level=0)
        yield df2.reset_index(level=1)
        yield df2.reset_index(level=[1, 0])
        yield df1.reset_index(level="month")
        yield df2.reset_index(level="year")
        yield df2.reset_index(level=["month", "year"])
        yield df2.reset_index(level="month", drop=True)
        yield df2.reset_index(level=["month", "year"], drop=True)

        self.assertRaisesRegex(
            IndexError,
            "Too many levels: Index has only 1 level, not 3",
            lambda: df1.reset_index(level=2),
        )
        self.assertRaisesRegex(
            IndexError,
            "Too many levels: Index has only 1 level, not 4",
            lambda: df1.reset_index(level=[3, 2]),
        )
        self.assertRaisesRegex(KeyError, "unknown.*month", lambda: df1.reset_index(level="unknown"))
        self.assertRaisesRegex(
            KeyError, "Level unknown not found", lambda: df2.reset_index(level="unknown")
        )

        df3 = df2.copy()
        df3.reset_index(inplace=True)
        yield df3

        yield df1.sale.reset_index()
        yield df1.sale.reset_index(level=0)
        yield df2.sale.reset_index(level=[1, 0])
        yield df1.sale.reset_index(drop=True)
        yield df1.sale.reset_index(name="s")
        yield df1.sale.reset_index(name="s", drop=True)

        s = df1.sale
        self.assertRaisesRegex(
            TypeError,
            "Cannot reset_index inplace on a Series to create a DataFrame",
            lambda: s.reset_index(inplace=True),
        )
        s.reset_index(drop=True, inplace=True)
        yield s
        yield df1

    def test_from_pandas_with_explicit_index(self):
        pdf = self.pdf

        df1 = ks.from_pandas(pdf.set_index("month"))
        self.assertPandasEqual(df1.to_pandas(), pdf.set_index("month"))

        df2 = ks.from_pandas(pdf.set_index(["year", "month"]))
        self.assertPandasEqual(df2.to_pandas(), pdf.set_index(["year", "month"]))

    def test_limitations(self):
        df = self.kdf.set_index("month")

        self.assertRaisesRegex(
            ValueError,
            "Level should be all int or all string.",
            lambda: df.reset_index([1, "month"]),
        )


class IndexingTest(ReusedSQLTestCase):
    @property
    def pdf(self):
        return pd.DataFrame(
            {"a": [1, 2, 3, 4, 5, 6, 7, 8, 9], "b": [4, 5, 6, 3, 2, 1, 0, 0, 0]},
            index=[0, 1, 3, 5, 6, 8, 9, 9, 9],
        )

    @property
    def kdf(self):
        return ks.from_pandas(self.pdf)

    @property
    def pdf2(self):
        return pd.DataFrame(
            {0: [1, 2, 3, 4, 5, 6, 7, 8, 9], 1: [4, 5, 6, 3, 2, 1, 0, 0, 0]},
            index=[0, 1, 3, 5, 6, 8, 9, 9, 9],
        )

    @property
    def kdf2(self):
        return ks.from_pandas(self.pdf2)

    def test_at(self):
        pdf = self.pdf
        kdf = self.kdf
        # Create the equivalent of pdf.loc[3] as a Koalas Series
        # This is necessary because .loc[n] does not currently work with Koalas DataFrames (#383)
        test_series = ks.Series([3, 6], index=["a", "b"], name="3")

        # Assert invalided signatures raise TypeError
        with self.assertRaises(TypeError, msg="Use DataFrame.at like .at[row_index, column_name]"):
            kdf.at[3]
        with self.assertRaises(TypeError, msg="Use DataFrame.at like .at[row_index, column_name]"):
            kdf.at["ab"]  # 'ab' is of length 2 but str type instead of tuple
        with self.assertRaises(TypeError, msg="Use Series.at like .at[column_name]"):
            test_series.at[3, "b"]

        # Assert .at for DataFrames
        self.assertEqual(kdf.at[3, "b"], 6)
        self.assertEqual(kdf.at[3, "b"], pdf.at[3, "b"])
        self.assert_eq(kdf.at[9, "b"], np.array([0, 0, 0]))
        self.assert_eq(kdf.at[9, "b"], pdf.at[9, "b"])

        # Assert .at for Series
        self.assertEqual(test_series.at["b"], 6)
        self.assertEqual(test_series.at["b"], pdf.loc[3].at["b"])

        # Assert multi-character indices
        self.assertEqual(
            ks.Series([0, 1], index=["ab", "cd"]).at["ab"],
            pd.Series([0, 1], index=["ab", "cd"]).at["ab"],
        )

        # Assert invalid column or index names result in a KeyError like with pandas
        with self.assertRaises(KeyError, msg="x"):
            kdf.at[3, "x"]
        with self.assertRaises(KeyError, msg=99):
            kdf.at[99, "b"]

        with self.assertRaises(ValueError):
            kdf.at[(3, 6), "b"]
        with self.assertRaises(KeyError):
            kdf.at[3, ("x", "b")]

        # Assert setting values fails
        with self.assertRaises(TypeError):
            kdf.at[3, "b"] = 10

        # non-string column names
        pdf = self.pdf2
        kdf = self.kdf2

        # Assert .at for DataFrames
        self.assertEqual(kdf.at[3, 1], 6)
        self.assertEqual(kdf.at[3, 1], pdf.at[3, 1])
        self.assert_eq(kdf.at[9, 1], np.array([0, 0, 0]))
        self.assert_eq(kdf.at[9, 1], pdf.at[9, 1])

    def test_at_multiindex(self):
        pdf = self.pdf.set_index("b", append=True)
        kdf = self.kdf.set_index("b", append=True)

        # TODO: seems like a pandas' bug in pandas>=1.1.0
        if LooseVersion(pd.__version__) < LooseVersion("1.1.0"):
            self.assert_eq(kdf.at[(3, 6), "a"], pdf.at[(3, 6), "a"])
            self.assert_eq(kdf.at[(3,), "a"], pdf.at[(3,), "a"])
            self.assert_eq(list(kdf.at[(9, 0), "a"]), list(pdf.at[(9, 0), "a"]))
            self.assert_eq(list(kdf.at[(9,), "a"]), list(pdf.at[(9,), "a"]))
        else:
            self.assert_eq(kdf.at[(3, 6), "a"], 3)
            self.assert_eq(kdf.at[(3,), "a"], np.array([3]))
            self.assert_eq(list(kdf.at[(9, 0), "a"]), [7, 8, 9])
            self.assert_eq(list(kdf.at[(9,), "a"]), [7, 8, 9])

        with self.assertRaises(ValueError):
            kdf.at[3, "a"]

    def test_at_multiindex_columns(self):
        arrays = [np.array(["bar", "bar", "baz", "baz"]), np.array(["one", "two", "one", "two"])]

        pdf = pd.DataFrame(np.random.randn(3, 4), index=["A", "B", "C"], columns=arrays)
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.at["B", ("bar", "one")], pdf.at["B", ("bar", "one")])

        with self.assertRaises(KeyError):
            kdf.at["B", "bar"]

        # non-string column names
        arrays = [np.array([0, 0, 1, 1]), np.array([1, 2, 1, 2])]

        pdf = pd.DataFrame(np.random.randn(3, 4), index=["A", "B", "C"], columns=arrays)
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.at["B", (0, 1)], pdf.at["B", (0, 1)])

    def test_iat(self):
        pdf = self.pdf
        kdf = self.kdf
        # Create the equivalent of pdf.loc[3] as a Koalas Series
        # This is necessary because .loc[n] does not currently work with Koalas DataFrames (#383)
        test_series = ks.Series([3, 6], index=["a", "b"], name="3")

        # Assert invalided signatures raise TypeError
        with self.assertRaises(
            TypeError,
            msg="Use DataFrame.at like .iat[row_interget_position, column_integer_position]",
        ):
            kdf.iat[3]
        with self.assertRaises(
            ValueError, msg="iAt based indexing on multi-index can only have tuple values"
        ):
            kdf.iat[3, "b"]  # 'ab' is of length 2 but str type instead of tuple
        with self.assertRaises(TypeError, msg="Use Series.iat like .iat[row_integer_position]"):
            test_series.iat[3, "b"]

        # Assert .iat for DataFrames
        self.assertEqual(kdf.iat[7, 0], 8)
        self.assertEqual(kdf.iat[7, 0], pdf.iat[7, 0])

        # Assert .iat for Series
        self.assertEqual(test_series.iat[1], 6)
        self.assertEqual(test_series.iat[1], pdf.loc[3].iat[1])

        # Assert invalid column or integer position result in a KeyError like with pandas
        with self.assertRaises(KeyError, msg=99):
            kdf.iat[0, 99]
        with self.assertRaises(KeyError, msg=99):
            kdf.iat[99, 0]

        with self.assertRaises(ValueError):
            kdf.iat[(1, 1), 1]
        with self.assertRaises(ValueError):
            kdf.iat[1, (1, 1)]

        # Assert setting values fails
        with self.assertRaises(TypeError):
            kdf.iat[4, 1] = 10

    def test_iat_multiindex(self):
        pdf = self.pdf.set_index("b", append=True)
        kdf = self.kdf.set_index("b", append=True)

        self.assert_eq(kdf.iat[7, 0], pdf.iat[7, 0])

        with self.assertRaises(ValueError):
            kdf.iat[3, "a"]

    def test_iat_multiindex_columns(self):
        arrays = [np.array(["bar", "bar", "baz", "baz"]), np.array(["one", "two", "one", "two"])]

        pdf = pd.DataFrame(np.random.randn(3, 4), index=["A", "B", "C"], columns=arrays)
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.iat[1, 3], pdf.iat[1, 3])

        with self.assertRaises(KeyError):
            kdf.iat[0, 99]
        with self.assertRaises(KeyError):
            kdf.iat[99, 0]

    def test_loc(self):
        kdf = self.kdf
        pdf = self.pdf

        self.assert_eq(kdf.loc[5:5], pdf.loc[5:5])
        self.assert_eq(kdf.loc[3:8], pdf.loc[3:8])
        self.assert_eq(kdf.loc[:8], pdf.loc[:8])
        self.assert_eq(kdf.loc[3:], pdf.loc[3:])
        self.assert_eq(kdf.loc[[5]], pdf.loc[[5]])
        self.assert_eq(kdf.loc[:], pdf.loc[:])

        # TODO?: self.assert_eq(kdf.loc[[3, 4, 1, 8]], pdf.loc[[3, 4, 1, 8]])
        # TODO?: self.assert_eq(kdf.loc[[3, 4, 1, 9]], pdf.loc[[3, 4, 1, 9]])
        # TODO?: self.assert_eq(kdf.loc[np.array([3, 4, 1, 9])], pdf.loc[np.array([3, 4, 1, 9])])

        self.assert_eq(kdf.a.loc[5:5], pdf.a.loc[5:5])
        self.assert_eq(kdf.a.loc[3:8], pdf.a.loc[3:8])
        self.assert_eq(kdf.a.loc[:8], pdf.a.loc[:8])
        self.assert_eq(kdf.a.loc[3:], pdf.a.loc[3:])
        self.assert_eq(kdf.a.loc[[5]], pdf.a.loc[[5]])

        # TODO?: self.assert_eq(kdf.a.loc[[3, 4, 1, 8]], pdf.a.loc[[3, 4, 1, 8]])
        # TODO?: self.assert_eq(kdf.a.loc[[3, 4, 1, 9]], pdf.a.loc[[3, 4, 1, 9]])
        # TODO?: self.assert_eq(kdf.a.loc[np.array([3, 4, 1, 9])],
        #                       pdf.a.loc[np.array([3, 4, 1, 9])])

        self.assert_eq(kdf.a.loc[[]], pdf.a.loc[[]])
        self.assert_eq(kdf.a.loc[np.array([])], pdf.a.loc[np.array([])])

        self.assert_eq(kdf.loc[1000:], pdf.loc[1000:])
        self.assert_eq(kdf.loc[-2000:-1000], pdf.loc[-2000:-1000])

        self.assert_eq(kdf.loc[5], pdf.loc[5])
        self.assert_eq(kdf.loc[9], pdf.loc[9])
        self.assert_eq(kdf.a.loc[5], pdf.a.loc[5])
        self.assert_eq(kdf.a.loc[9], pdf.a.loc[9])

        self.assertRaises(KeyError, lambda: kdf.loc[10])
        self.assertRaises(KeyError, lambda: kdf.a.loc[10])

        # monotonically increasing index test
        pdf = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6, 7, 8, 9]}, index=[0, 1, 1, 2, 2, 2, 4, 5, 6])
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc[:2], pdf.loc[:2])
        self.assert_eq(kdf.loc[:3], pdf.loc[:3])
        self.assert_eq(kdf.loc[3:], pdf.loc[3:])
        self.assert_eq(kdf.loc[4:], pdf.loc[4:])
        self.assert_eq(kdf.loc[3:2], pdf.loc[3:2])
        self.assert_eq(kdf.loc[-1:2], pdf.loc[-1:2])
        self.assert_eq(kdf.loc[3:10], pdf.loc[3:10])

        # monotonically decreasing index test
        pdf = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6, 7, 8, 9]}, index=[6, 5, 5, 4, 4, 4, 2, 1, 0])
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc[:4], pdf.loc[:4])
        self.assert_eq(kdf.loc[:3], pdf.loc[:3])
        self.assert_eq(kdf.loc[3:], pdf.loc[3:])
        self.assert_eq(kdf.loc[2:], pdf.loc[2:])
        self.assert_eq(kdf.loc[2:3], pdf.loc[2:3])
        self.assert_eq(kdf.loc[2:-1], pdf.loc[2:-1])
        self.assert_eq(kdf.loc[10:3], pdf.loc[10:3])

        # test when type of key is string and given value is not included in key
        pdf = pd.DataFrame({"a": [1, 2, 3]}, index=["a", "b", "d"])
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc["a":"z"], pdf.loc["a":"z"])

        # KeyError when index is not monotonic increasing or decreasing
        # and specified values don't exist in index
        kdf = ks.DataFrame([[1, 2], [4, 5], [7, 8]], index=["cobra", "viper", "sidewinder"])

        self.assertRaises(KeyError, lambda: kdf.loc["cobra":"koalas"])
        self.assertRaises(KeyError, lambda: kdf.loc["koalas":"viper"])

        kdf = ks.DataFrame([[1, 2], [4, 5], [7, 8]], index=[10, 30, 20])

        self.assertRaises(KeyError, lambda: kdf.loc[0:30])
        self.assertRaises(KeyError, lambda: kdf.loc[10:100])

    def test_loc_non_informative_index(self):
        pdf = pd.DataFrame({"x": [1, 2, 3, 4]}, index=[10, 20, 30, 40])
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc[20:30], pdf.loc[20:30])

        pdf = pd.DataFrame({"x": [1, 2, 3, 4]}, index=[10, 20, 20, 40])
        kdf = ks.from_pandas(pdf)
        self.assert_eq(kdf.loc[20:20], pdf.loc[20:20])

    def test_loc_with_series(self):
        kdf = self.kdf
        pdf = self.pdf

        self.assert_eq(kdf.loc[kdf.a % 2 == 0], pdf.loc[pdf.a % 2 == 0])
        self.assert_eq(kdf.loc[kdf.a % 2 == 0, "a"], pdf.loc[pdf.a % 2 == 0, "a"])
        self.assert_eq(kdf.loc[kdf.a % 2 == 0, ["a"]], pdf.loc[pdf.a % 2 == 0, ["a"]])
        self.assert_eq(kdf.a.loc[kdf.a % 2 == 0], pdf.a.loc[pdf.a % 2 == 0])

        self.assert_eq(kdf.loc[kdf.copy().a % 2 == 0], pdf.loc[pdf.copy().a % 2 == 0])
        self.assert_eq(kdf.loc[kdf.copy().a % 2 == 0, "a"], pdf.loc[pdf.copy().a % 2 == 0, "a"])
        self.assert_eq(kdf.loc[kdf.copy().a % 2 == 0, ["a"]], pdf.loc[pdf.copy().a % 2 == 0, ["a"]])
        self.assert_eq(kdf.a.loc[kdf.copy().a % 2 == 0], pdf.a.loc[pdf.copy().a % 2 == 0])

    def test_loc_noindex(self):
        kdf = self.kdf
        kdf = kdf.reset_index()
        pdf = self.pdf
        pdf = pdf.reset_index()

        self.assert_eq(kdf[["a"]], pdf[["a"]])

        self.assert_eq(kdf.loc[:], pdf.loc[:])
        self.assert_eq(kdf.loc[5:5], pdf.loc[5:5])

    def test_loc_multiindex(self):
        kdf = self.kdf
        kdf = kdf.set_index("b", append=True)
        pdf = self.pdf
        pdf = pdf.set_index("b", append=True)

        self.assert_eq(kdf.loc[:], pdf.loc[:])
        self.assert_eq(kdf.loc[5:5], pdf.loc[5:5])
        self.assert_eq(kdf.loc[5:9], pdf.loc[5:9])

        self.assert_eq(kdf.loc[5], pdf.loc[5])
        self.assert_eq(kdf.loc[9], pdf.loc[9])
        # TODO: self.assert_eq(kdf.loc[(5, 3)], pdf.loc[(5, 3)])
        # TODO: self.assert_eq(kdf.loc[(9, 0)], pdf.loc[(9, 0)])
        self.assert_eq(kdf.a.loc[5], pdf.a.loc[5])
        self.assert_eq(kdf.a.loc[9], pdf.a.loc[9])
        self.assertTrue((kdf.a.loc[(5, 3)] == pdf.a.loc[(5, 3)]).all())
        self.assert_eq(kdf.a.loc[(9, 0)], pdf.a.loc[(9, 0)])

        # monotonically increasing index test
        pdf = pd.DataFrame(
            {"a": [1, 2, 3, 4, 5]},
            index=pd.MultiIndex.from_tuples(
                [("x", "a"), ("x", "b"), ("y", "c"), ("y", "d"), ("z", "e")]
            ),
        )
        kdf = ks.from_pandas(pdf)

        for rows_sel in [
            slice(None),
            slice("y", None),
            slice(None, "y"),
            slice(("x", "b"), None),
            slice(None, ("y", "c")),
            slice(("x", "b"), ("y", "c")),
            slice("x", ("y", "c")),
            slice(("x", "b"), "y"),
        ]:
            with self.subTest("monotonically increasing", rows_sel=rows_sel):
                self.assert_eq(kdf.loc[rows_sel], pdf.loc[rows_sel])
                self.assert_eq(kdf.a.loc[rows_sel], pdf.a.loc[rows_sel])

        # monotonically increasing first index test
        pdf = pd.DataFrame(
            {"a": [1, 2, 3, 4, 5]},
            index=pd.MultiIndex.from_tuples(
                [("x", "a"), ("x", "b"), ("y", "c"), ("y", "a"), ("z", "e")]
            ),
        )
        kdf = ks.from_pandas(pdf)

        for rows_sel in [
            slice(None),
            slice("y", None),
            slice(None, "y"),
        ]:
            with self.subTest("monotonically increasing first index", rows_sel=rows_sel):
                self.assert_eq(kdf.loc[rows_sel], pdf.loc[rows_sel])
                self.assert_eq(kdf.a.loc[rows_sel], pdf.a.loc[rows_sel])

        for rows_sel in [
            slice(("x", "b"), None),
            slice(None, ("y", "c")),
            slice(("x", "b"), ("y", "c")),
            slice("x", ("y", "c")),
            slice(("x", "b"), "y"),
        ]:
            with self.subTest("monotonically increasing first index", rows_sel=rows_sel):
                self.assertRaises(KeyError, lambda: kdf.loc[rows_sel])
                self.assertRaises(KeyError, lambda: kdf.a.loc[rows_sel])

        # not monotonically increasing index test
        pdf = pd.DataFrame(
            {"a": [1, 2, 3, 4, 5]},
            index=pd.MultiIndex.from_tuples(
                [("z", "e"), ("y", "d"), ("y", "c"), ("x", "b"), ("x", "a")]
            ),
        )
        kdf = ks.from_pandas(pdf)

        for rows_sel in [
            slice("y", None),
            slice(None, "y"),
            slice(("x", "b"), None),
            slice(None, ("y", "c")),
            slice(("x", "b"), ("y", "c")),
            slice("x", ("y", "c")),
            slice(("x", "b"), "y"),
        ]:
            with self.subTest("monotonically decreasing", rows_sel=rows_sel):
                self.assertRaises(KeyError, lambda: kdf.loc[rows_sel])
                self.assertRaises(KeyError, lambda: kdf.a.loc[rows_sel])

    def test_loc2d_multiindex(self):
        kdf = self.kdf
        kdf = kdf.set_index("b", append=True)
        pdf = self.pdf
        pdf = pdf.set_index("b", append=True)

        self.assert_eq(kdf.loc[:, :], pdf.loc[:, :])
        self.assert_eq(kdf.loc[:, "a"], pdf.loc[:, "a"])
        self.assert_eq(kdf.loc[5:5, "a"], pdf.loc[5:5, "a"])

        self.assert_eq(kdf.loc[:, "a":"a"], pdf.loc[:, "a":"a"])
        self.assert_eq(kdf.loc[:, "a":"c"], pdf.loc[:, "a":"c"])
        self.assert_eq(kdf.loc[:, "b":"c"], pdf.loc[:, "b":"c"])

    def test_loc2d(self):
        kdf = self.kdf
        pdf = self.pdf

        # index indexer is always regarded as slice for duplicated values
        self.assert_eq(kdf.loc[5:5, "a"], pdf.loc[5:5, "a"])
        self.assert_eq(kdf.loc[[5], "a"], pdf.loc[[5], "a"])
        self.assert_eq(kdf.loc[5:5, ["a"]], pdf.loc[5:5, ["a"]])
        self.assert_eq(kdf.loc[[5], ["a"]], pdf.loc[[5], ["a"]])
        self.assert_eq(kdf.loc[:, :], pdf.loc[:, :])

        self.assert_eq(kdf.loc[3:8, "a"], pdf.loc[3:8, "a"])
        self.assert_eq(kdf.loc[:8, "a"], pdf.loc[:8, "a"])
        self.assert_eq(kdf.loc[3:, "a"], pdf.loc[3:, "a"])
        self.assert_eq(kdf.loc[[8], "a"], pdf.loc[[8], "a"])

        self.assert_eq(kdf.loc[3:8, ["a"]], pdf.loc[3:8, ["a"]])
        self.assert_eq(kdf.loc[:8, ["a"]], pdf.loc[:8, ["a"]])
        self.assert_eq(kdf.loc[3:, ["a"]], pdf.loc[3:, ["a"]])
        # TODO?: self.assert_eq(kdf.loc[[3, 4, 3], ['a']], pdf.loc[[3, 4, 3], ['a']])

        self.assertRaises(SparkPandasIndexingError, lambda: kdf.loc[3, 3, 3])
        self.assertRaises(SparkPandasIndexingError, lambda: kdf.a.loc[3, 3])
        self.assertRaises(SparkPandasIndexingError, lambda: kdf.a.loc[3:, 3])
        self.assertRaises(SparkPandasIndexingError, lambda: kdf.a.loc[kdf.a % 2 == 0, 3])

        self.assert_eq(kdf.loc[5, "a"], pdf.loc[5, "a"])
        self.assert_eq(kdf.loc[9, "a"], pdf.loc[9, "a"])
        self.assert_eq(kdf.loc[5, ["a"]], pdf.loc[5, ["a"]])
        self.assert_eq(kdf.loc[9, ["a"]], pdf.loc[9, ["a"]])

        self.assert_eq(kdf.loc[:, "a":"a"], pdf.loc[:, "a":"a"])
        self.assert_eq(kdf.loc[:, "a":"d"], pdf.loc[:, "a":"d"])
        self.assert_eq(kdf.loc[:, "c":"d"], pdf.loc[:, "c":"d"])

        # non-string column names
        kdf = self.kdf2
        pdf = self.pdf2

        self.assert_eq(kdf.loc[5:5, 0], pdf.loc[5:5, 0])
        self.assert_eq(kdf.loc[5:5, [0]], pdf.loc[5:5, [0]])
        self.assert_eq(kdf.loc[3:8, 0], pdf.loc[3:8, 0])
        self.assert_eq(kdf.loc[3:8, [0]], pdf.loc[3:8, [0]])

        self.assert_eq(kdf.loc[:, 0:0], pdf.loc[:, 0:0])
        self.assert_eq(kdf.loc[:, 0:3], pdf.loc[:, 0:3])
        self.assert_eq(kdf.loc[:, 2:3], pdf.loc[:, 2:3])

    def test_loc2d_multiindex_columns(self):
        arrays = [np.array(["bar", "bar", "baz", "baz"]), np.array(["one", "two", "one", "two"])]

        pdf = pd.DataFrame(np.random.randn(3, 4), index=["A", "B", "C"], columns=arrays)
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc["B":"B", "bar"], pdf.loc["B":"B", "bar"])
        self.assert_eq(kdf.loc["B":"B", ["bar"]], pdf.loc["B":"B", ["bar"]])

        self.assert_eq(kdf.loc[:, "bar":"bar"], pdf.loc[:, "bar":"bar"])
        self.assert_eq(kdf.loc[:, "bar":("baz", "one")], pdf.loc[:, "bar":("baz", "one")])
        self.assert_eq(
            kdf.loc[:, ("bar", "two"):("baz", "one")], pdf.loc[:, ("bar", "two"):("baz", "one")]
        )
        self.assert_eq(kdf.loc[:, ("bar", "two"):"bar"], pdf.loc[:, ("bar", "two"):"bar"])
        self.assert_eq(kdf.loc[:, "a":"bax"], pdf.loc[:, "a":"bax"])
        self.assert_eq(
            kdf.loc[:, ("bar", "x"):("baz", "a")],
            pdf.loc[:, ("bar", "x"):("baz", "a")],
            almost=True,
        )

        pdf = pd.DataFrame(
            np.random.randn(3, 4),
            index=["A", "B", "C"],
            columns=pd.MultiIndex.from_tuples(
                [("bar", "two"), ("bar", "one"), ("baz", "one"), ("baz", "two")]
            ),
        )
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc[:, "bar":"baz"], pdf.loc[:, "bar":"baz"])

        self.assertRaises(KeyError, lambda: kdf.loc[:, "bar":("baz", "one")])
        self.assertRaises(KeyError, lambda: kdf.loc[:, ("bar", "two"):"bar"])

        # non-string column names
        arrays = [np.array([0, 0, 1, 1]), np.array([1, 2, 1, 2])]

        pdf = pd.DataFrame(np.random.randn(3, 4), index=["A", "B", "C"], columns=arrays)
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc["B":"B", 0], pdf.loc["B":"B", 0])
        self.assert_eq(kdf.loc["B":"B", [0]], pdf.loc["B":"B", [0]])
        self.assert_eq(kdf.loc[:, 0:0], pdf.loc[:, 0:0])
        self.assert_eq(kdf.loc[:, 0:(1, 1)], pdf.loc[:, 0:(1, 1)])
        self.assert_eq(kdf.loc[:, (0, 2):(1, 1)], pdf.loc[:, (0, 2):(1, 1)])
        self.assert_eq(kdf.loc[:, (0, 2):0], pdf.loc[:, (0, 2):0])
        self.assert_eq(kdf.loc[:, -1:2], pdf.loc[:, -1:2])

    def test_loc2d_with_known_divisions(self):
        pdf = pd.DataFrame(
            np.random.randn(20, 5), index=list("abcdefghijklmnopqrst"), columns=list("ABCDE")
        )
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc[["a"], "A"], pdf.loc[["a"], "A"])
        self.assert_eq(kdf.loc[["a"], ["A"]], pdf.loc[["a"], ["A"]])
        self.assert_eq(kdf.loc["a":"o", "A"], pdf.loc["a":"o", "A"])
        self.assert_eq(kdf.loc["a":"o", ["A"]], pdf.loc["a":"o", ["A"]])
        self.assert_eq(kdf.loc[["n"], ["A"]], pdf.loc[["n"], ["A"]])
        self.assert_eq(kdf.loc[["a", "c", "n"], ["A"]], pdf.loc[["a", "c", "n"], ["A"]])
        # TODO?: self.assert_eq(kdf.loc[['t', 'b'], ['A']], pdf.loc[['t', 'b'], ['A']])
        # TODO?: self.assert_eq(kdf.loc[['r', 'r', 'c', 'g', 'h'], ['A']],
        # TODO?:                pdf.loc[['r', 'r', 'c', 'g', 'h'], ['A']])

    @unittest.skip("TODO: should handle duplicated columns properly")
    def test_loc2d_duplicated_columns(self):
        pdf = pd.DataFrame(
            np.random.randn(20, 5), index=list("abcdefghijklmnopqrst"), columns=list("AABCD")
        )
        kdf = ks.from_pandas(pdf)

        # TODO?: self.assert_eq(kdf.loc[['a'], 'A'], pdf.loc[['a'], 'A'])
        # TODO?: self.assert_eq(kdf.loc[['a'], ['A']], pdf.loc[['a'], ['A']])
        self.assert_eq(kdf.loc[["j"], "B"], pdf.loc[["j"], "B"])
        self.assert_eq(kdf.loc[["j"], ["B"]], pdf.loc[["j"], ["B"]])

        # TODO?: self.assert_eq(kdf.loc['a':'o', 'A'], pdf.loc['a':'o', 'A'])
        # TODO?: self.assert_eq(kdf.loc['a':'o', ['A']], pdf.loc['a':'o', ['A']])
        self.assert_eq(kdf.loc["j":"q", "B"], pdf.loc["j":"q", "B"])
        self.assert_eq(kdf.loc["j":"q", ["B"]], pdf.loc["j":"q", ["B"]])

        # TODO?: self.assert_eq(kdf.loc['a':'o', 'B':'D'], pdf.loc['a':'o', 'B':'D'])
        # TODO?: self.assert_eq(kdf.loc['a':'o', 'B':'D'], pdf.loc['a':'o', 'B':'D'])
        # TODO?: self.assert_eq(kdf.loc['j':'q', 'B':'A'], pdf.loc['j':'q', 'B':'A'])
        # TODO?: self.assert_eq(kdf.loc['j':'q', 'B':'A'], pdf.loc['j':'q', 'B':'A'])

        self.assert_eq(kdf.loc[kdf.B > 0, "B"], pdf.loc[pdf.B > 0, "B"])
        # TODO?: self.assert_eq(kdf.loc[kdf.B > 0, ['A', 'C']], pdf.loc[pdf.B > 0, ['A', 'C']])

    def test_getitem(self):
        pdf = pd.DataFrame(
            {
                "A": [1, 2, 3, 4, 5, 6, 7, 8, 9],
                "B": [9, 8, 7, 6, 5, 4, 3, 2, 1],
                "C": [True, False, True] * 3,
            },
            columns=list("ABC"),
        )
        kdf = ks.from_pandas(pdf)
        self.assert_eq(kdf["A"], pdf["A"])

        self.assert_eq(kdf[["A", "B"]], pdf[["A", "B"]])

        self.assert_eq(kdf[kdf.C], pdf[pdf.C])

        self.assertRaises(KeyError, lambda: kdf["X"])
        self.assertRaises(KeyError, lambda: kdf[["A", "X"]])
        self.assertRaises(AttributeError, lambda: kdf.X)

        # not str/unicode
        # TODO?: pdf = pd.DataFrame(np.random.randn(10, 5))
        # TODO?: kdf = ks.from_pandas(pdf)
        # TODO?: self.assert_eq(kdf[0], pdf[0])
        # TODO?: self.assert_eq(kdf[[1, 2]], pdf[[1, 2]])

        # TODO?: self.assertRaises(KeyError, lambda: pdf[8])
        # TODO?: self.assertRaises(KeyError, lambda: pdf[[1, 8]])

        # non-string column names
        pdf = pd.DataFrame(
            {
                10: [1, 2, 3, 4, 5, 6, 7, 8, 9],
                20: [9, 8, 7, 6, 5, 4, 3, 2, 1],
                30: [True, False, True] * 3,
            }
        )
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf[10], pdf[10])
        self.assert_eq(kdf[[10, 20]], pdf[[10, 20]])

    def test_getitem_slice(self):
        pdf = pd.DataFrame(
            {
                "A": [1, 2, 3, 4, 5, 6, 7, 8, 9],
                "B": [9, 8, 7, 6, 5, 4, 3, 2, 1],
                "C": [True, False, True] * 3,
            },
            index=list("abcdefghi"),
        )
        kdf = ks.from_pandas(pdf)
        self.assert_eq(kdf["a":"e"], pdf["a":"e"])
        self.assert_eq(kdf["a":"b"], pdf["a":"b"])
        self.assert_eq(kdf["f":], pdf["f":])

    def test_loc_on_numpy_datetimes(self):
        pdf = pd.DataFrame(
            {"x": [1, 2, 3]}, index=list(map(np.datetime64, ["2014", "2015", "2016"]))
        )
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc["2014":"2015"], pdf.loc["2014":"2015"])

    def test_loc_on_pandas_datetimes(self):
        pdf = pd.DataFrame(
            {"x": [1, 2, 3]}, index=list(map(pd.Timestamp, ["2014", "2015", "2016"]))
        )
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.loc["2014":"2015"], pdf.loc["2014":"2015"])

    @unittest.skip("TODO?: the behavior of slice for datetime")
    def test_loc_datetime_no_freq(self):
        datetime_index = pd.date_range("2016-01-01", "2016-01-31", freq="12h")
        datetime_index.freq = None  # FORGET FREQUENCY
        pdf = pd.DataFrame({"num": range(len(datetime_index))}, index=datetime_index)
        kdf = ks.from_pandas(pdf)

        slice_ = slice("2016-01-03", "2016-01-05")
        result = kdf.loc[slice_, :]
        expected = pdf.loc[slice_, :]
        self.assert_eq(result, expected)

    @unittest.skip("TODO?: the behavior of slice for datetime")
    def test_loc_timestamp_str(self):
        pdf = pd.DataFrame(
            {"A": np.random.randn(100), "B": np.random.randn(100)},
            index=pd.date_range("2011-01-01", freq="H", periods=100),
        )
        kdf = ks.from_pandas(pdf)

        # partial string slice
        # TODO?: self.assert_eq(pdf.loc['2011-01-02'],
        # TODO?:                kdf.loc['2011-01-02'])
        self.assert_eq(pdf.loc["2011-01-02":"2011-01-05"], kdf.loc["2011-01-02":"2011-01-05"])

        # series
        # TODO?: self.assert_eq(pdf.A.loc['2011-01-02'],
        # TODO?:                kdf.A.loc['2011-01-02'])
        self.assert_eq(pdf.A.loc["2011-01-02":"2011-01-05"], kdf.A.loc["2011-01-02":"2011-01-05"])

        pdf = pd.DataFrame(
            {"A": np.random.randn(100), "B": np.random.randn(100)},
            index=pd.date_range("2011-01-01", freq="M", periods=100),
        )
        kdf = ks.from_pandas(pdf)
        # TODO?: self.assert_eq(pdf.loc['2011-01'], kdf.loc['2011-01'])
        # TODO?: self.assert_eq(pdf.loc['2011'], kdf.loc['2011'])

        self.assert_eq(pdf.loc["2011-01":"2012-05"], kdf.loc["2011-01":"2012-05"])
        self.assert_eq(pdf.loc["2011":"2015"], kdf.loc["2011":"2015"])

        # series
        # TODO?: self.assert_eq(pdf.B.loc['2011-01'], kdf.B.loc['2011-01'])
        # TODO?: self.assert_eq(pdf.B.loc['2011'], kdf.B.loc['2011'])

        self.assert_eq(pdf.B.loc["2011-01":"2012-05"], kdf.B.loc["2011-01":"2012-05"])
        self.assert_eq(pdf.B.loc["2011":"2015"], kdf.B.loc["2011":"2015"])

    @unittest.skip("TODO?: the behavior of slice for datetime")
    def test_getitem_timestamp_str(self):
        pdf = pd.DataFrame(
            {"A": np.random.randn(100), "B": np.random.randn(100)},
            index=pd.date_range("2011-01-01", freq="H", periods=100),
        )
        kdf = ks.from_pandas(pdf)

        # partial string slice
        # TODO?: self.assert_eq(pdf['2011-01-02'],
        # TODO?:                kdf['2011-01-02'])
        self.assert_eq(pdf["2011-01-02":"2011-01-05"], kdf["2011-01-02":"2011-01-05"])

        pdf = pd.DataFrame(
            {"A": np.random.randn(100), "B": np.random.randn(100)},
            index=pd.date_range("2011-01-01", freq="M", periods=100),
        )
        kdf = ks.from_pandas(pdf)

        # TODO?: self.assert_eq(pdf['2011-01'], kdf['2011-01'])
        # TODO?: self.assert_eq(pdf['2011'], kdf['2011'])

        self.assert_eq(pdf["2011-01":"2012-05"], kdf["2011-01":"2012-05"])
        self.assert_eq(pdf["2011":"2015"], kdf["2011":"2015"])

    @unittest.skip("TODO?: period index can't convert to DataFrame correctly")
    def test_getitem_period_str(self):
        pdf = pd.DataFrame(
            {"A": np.random.randn(100), "B": np.random.randn(100)},
            index=pd.period_range("2011-01-01", freq="H", periods=100),
        )
        kdf = ks.from_pandas(pdf)

        # partial string slice
        # TODO?: self.assert_eq(pdf['2011-01-02'],
        # TODO?:                kdf['2011-01-02'])
        self.assert_eq(pdf["2011-01-02":"2011-01-05"], kdf["2011-01-02":"2011-01-05"])

        pdf = pd.DataFrame(
            {"A": np.random.randn(100), "B": np.random.randn(100)},
            index=pd.period_range("2011-01-01", freq="M", periods=100),
        )
        kdf = ks.from_pandas(pdf)

        # TODO?: self.assert_eq(pdf['2011-01'], kdf['2011-01'])
        # TODO?: self.assert_eq(pdf['2011'], kdf['2011'])

        self.assert_eq(pdf["2011-01":"2012-05"], kdf["2011-01":"2012-05"])
        self.assert_eq(pdf["2011":"2015"], kdf["2011":"2015"])

    def test_iloc(self):
        pdf = pd.DataFrame({"A": [1, 2], "B": [3, 4], "C": [5, 6]})
        kdf = ks.from_pandas(pdf)

        self.assert_eq(kdf.iloc[0, 0], pdf.iloc[0, 0])
        for indexer in [0, [0], [0, 1], [1, 0], [False, True, True], slice(0, 1)]:
            self.assert_eq(kdf.iloc[:, indexer], pdf.iloc[:, indexer])
            self.assert_eq(kdf.iloc[:1, indexer], pdf.iloc[:1, indexer])
            self.assert_eq(kdf.iloc[:-1, indexer], pdf.iloc[:-1, indexer])
            # self.assert_eq(kdf.iloc[kdf.index == 2, indexer], pdf.iloc[pdf.index == 2, indexer])

    def test_iloc_multiindex_columns(self):
        arrays = [np.array(["bar", "bar", "baz", "baz"]), np.array(["one", "two", "one", "two"])]

        pdf = pd.DataFrame(np.random.randn(3, 4), index=["A", "B", "C"], columns=arrays)
        kdf = ks.from_pandas(pdf)

        for indexer in [0, [0], [0, 1], [1, 0], [False, True, True, True], slice(0, 1)]:
            self.assert_eq(kdf.iloc[:, indexer], pdf.iloc[:, indexer])
            self.assert_eq(kdf.iloc[:1, indexer], pdf.iloc[:1, indexer])
            self.assert_eq(kdf.iloc[:-1, indexer], pdf.iloc[:-1, indexer])
            # self.assert_eq(kdf.iloc[kdf.index == "B", indexer],
            #                pdf.iloc[pdf.index == "B", indexer])

    def test_iloc_series(self):
        pser = pd.Series([1, 2, 3])
        kser = ks.from_pandas(pser)

        self.assert_eq(kser.iloc[0], pser.iloc[0])
        self.assert_eq(kser.iloc[:], pser.iloc[:])
        self.assert_eq(kser.iloc[:1], pser.iloc[:1])
        self.assert_eq(kser.iloc[:-1], pser.iloc[:-1])

        self.assert_eq((kser + 1).iloc[0], (pser + 1).iloc[0])
        self.assert_eq((kser + 1).iloc[:], (pser + 1).iloc[:])
        self.assert_eq((kser + 1).iloc[:1], (pser + 1).iloc[:1])
        self.assert_eq((kser + 1).iloc[:-1], (pser + 1).iloc[:-1])

    def test_iloc_slice_rows_sel(self):
        pdf = pd.DataFrame({"A": [1, 2] * 5, "B": [3, 4] * 5, "C": [5, 6] * 5})
        kdf = ks.from_pandas(pdf)

        for rows_sel in [
            slice(None),
            slice(0, 1),
            slice(1, 2),
            slice(-3, None),
            slice(None, -3),
            slice(None, 0),
            slice(None, None, 3),
            slice(3, 8, 2),
            slice(None, None, -2),
            slice(8, 3, -2),
            slice(8, None, -2),
            slice(None, 3, -2),
        ]:
            with self.subTest(rows_sel=rows_sel):
                self.assert_eq(kdf.iloc[rows_sel].sort_index(), pdf.iloc[rows_sel].sort_index())
                self.assert_eq(kdf.A.iloc[rows_sel].sort_index(), pdf.A.iloc[rows_sel].sort_index())
                self.assert_eq(
                    (kdf.A + 1).iloc[rows_sel].sort_index(), (pdf.A + 1).iloc[rows_sel].sort_index()
                )

    def test_iloc_iterable_rows_sel(self):
        pdf = pd.DataFrame({"A": [1, 2] * 5, "B": [3, 4] * 5, "C": [5, 6] * 5})
        kdf = ks.from_pandas(pdf)

        for rows_sel in [
            [],
            np.array([0, 1]),
            [1, 2],
            np.array([-3]),
            [3],
            np.array([-2]),
            [8, 3, -5],
        ]:
            with self.subTest(rows_sel=rows_sel):
                self.assert_eq(kdf.iloc[rows_sel].sort_index(), pdf.iloc[rows_sel].sort_index())
                self.assert_eq(kdf.A.iloc[rows_sel].sort_index(), pdf.A.iloc[rows_sel].sort_index())
                self.assert_eq(
                    (kdf.A + 1).iloc[rows_sel].sort_index(), (pdf.A + 1).iloc[rows_sel].sort_index()
                )

            with self.subTest(rows_sel=rows_sel):
                self.assert_eq(
                    kdf.iloc[rows_sel, :].sort_index(), pdf.iloc[rows_sel, :].sort_index()
                )

            with self.subTest(rows_sel=rows_sel):
                self.assert_eq(
                    kdf.iloc[rows_sel, :1].sort_index(), pdf.iloc[rows_sel, :1].sort_index()
                )

    def test_frame_loc_setitem(self):
        pdf = pd.DataFrame(
            [[1, 2], [4, 5], [7, 8]],
            index=["cobra", "viper", "sidewinder"],
            columns=["max_speed", "shield"],
        )
        kdf = ks.from_pandas(pdf)

        pser1 = pdf.max_speed
        pser2 = pdf.shield
        kser1 = kdf.max_speed
        kser2 = kdf.shield

        pdf.loc[["viper", "sidewinder"], ["shield", "max_speed"]] = 10
        kdf.loc[["viper", "sidewinder"], ["shield", "max_speed"]] = 10
        self.assert_eq(kdf, pdf)
        self.assert_eq(kser1, pser1)
        self.assert_eq(kser2, pser2)

        pdf.loc[["viper", "sidewinder"], "shield"] = 50
        kdf.loc[["viper", "sidewinder"], "shield"] = 50
        self.assert_eq(kdf, pdf)
        self.assert_eq(kser1, pser1)
        self.assert_eq(kser2, pser2)

        pdf.loc["cobra", "max_speed"] = 30
        kdf.loc["cobra", "max_speed"] = 30
        self.assert_eq(kdf, pdf)
        self.assert_eq(kser1, pser1)
        self.assert_eq(kser2, pser2)

        pdf.loc[pdf.max_speed < 5, "max_speed"] = -pdf.max_speed
        kdf.loc[kdf.max_speed < 5, "max_speed"] = -kdf.max_speed
        self.assert_eq(kdf, pdf)
        self.assert_eq(kser1, pser1)
        self.assert_eq(kser2, pser2)

        pdf.loc[pdf.max_speed < 2, "max_speed"] = -pdf.max_speed
        kdf.loc[kdf.max_speed < 2, "max_speed"] = -kdf.max_speed
        self.assert_eq(kdf, pdf)
        self.assert_eq(kser1, pser1)
        self.assert_eq(kser2, pser2)

        pdf.loc[:, "min_speed"] = 0
        kdf.loc[:, "min_speed"] = 0
        self.assert_eq(kdf, pdf, almost=True)
        self.assert_eq(kser1, pser1)
        self.assert_eq(kser2, pser2)

        with self.assertRaisesRegex(ValueError, "Incompatible indexer with Series"):
            kdf.loc["cobra", "max_speed"] = -kdf.max_speed
        with self.assertRaisesRegex(ValueError, "shape mismatch"):
            kdf.loc[:, ["shield", "max_speed"]] = -kdf.max_speed
        with self.assertRaisesRegex(ValueError, "Only a dataframe with one column can be assigned"):
            kdf.loc[:, "max_speed"] = kdf

        # multi-index columns
        columns = pd.MultiIndex.from_tuples(
            [("x", "max_speed"), ("x", "shield"), ("y", "min_speed")]
        )
        pdf.columns = columns
        kdf.columns = columns

        pdf.loc[:, ("y", "shield")] = -pdf[("x", "shield")]
        kdf.loc[:, ("y", "shield")] = -kdf[("x", "shield")]
        self.assert_eq(kdf, pdf, almost=True)
        self.assert_eq(kser1, pser1)
        self.assert_eq(kser2, pser2)

        pdf.loc[:, "z"] = 100
        kdf.loc[:, "z"] = 100
        self.assert_eq(kdf, pdf, almost=True)
        self.assert_eq(kser1, pser1)
        self.assert_eq(kser2, pser2)

        with self.assertRaisesRegex(KeyError, "Key length \\(3\\) exceeds index depth \\(2\\)"):
            kdf.loc[:, [("x", "max_speed", "foo")]] = -kdf[("x", "shield")]

        pdf = pd.DataFrame(
            [[1], [4], [7]], index=["cobra", "viper", "sidewinder"], columns=["max_speed"]
        )
        kdf = ks.from_pandas(pdf)

        pdf.loc[:, "max_speed"] = pdf
        kdf.loc[:, "max_speed"] = kdf
        self.assert_eq(kdf, pdf)

    def test_frame_iloc_setitem(self):
        pdf = pd.DataFrame(
            [[1, 2], [4, 5], [7, 8]],
            index=["cobra", "viper", "sidewinder"],
            columns=["max_speed", "shield"],
        )
        kdf = ks.from_pandas(pdf)

        pdf.iloc[[1, 2], [1, 0]] = 10
        kdf.iloc[[1, 2], [1, 0]] = 10
        self.assert_eq(kdf, pdf)

        pdf.iloc[0, 1] = 50
        kdf.iloc[0, 1] = 50
        self.assert_eq(kdf, pdf)

        with self.assertRaisesRegex(ValueError, "Incompatible indexer with Series"):
            kdf.iloc[0, 0] = -kdf.max_speed
        with self.assertRaisesRegex(ValueError, "shape mismatch"):
            kdf.iloc[:, [1, 0]] = -kdf.max_speed
        with self.assertRaisesRegex(ValueError, "Only a dataframe with one column can be assigned"):
            kdf.iloc[:, 0] = kdf

        pdf = pd.DataFrame(
            [[1], [4], [7]], index=["cobra", "viper", "sidewinder"], columns=["max_speed"]
        )
        kdf = ks.from_pandas(pdf)

        pdf.iloc[:, 0] = pdf
        kdf.iloc[:, 0] = kdf
        self.assert_eq(kdf, pdf)

    def test_series_loc_setitem(self):
        pdf = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]}, index=["cobra", "viper", "sidewinder"])
        kdf = ks.from_pandas(pdf)

        pser = pdf.x
        psery = pdf.y
        kser = kdf.x
        ksery = kdf.y

        pser.loc[pser % 2 == 1] = -pser
        kser.loc[kser % 2 == 1] = -kser
        self.assert_eq(kser, pser)
        self.assert_eq(kdf, pdf)
        self.assert_eq(ksery, psery)

        for key, value in [
            (["viper", "sidewinder"], 10),
            ("viper", 50),
            (slice(None), 10),
            (slice(None, "viper"), 20),
            (slice("viper", None), 30),
        ]:
            with self.subTest(key=key, value=value):
                pser.loc[key] = value
                kser.loc[key] = value
                self.assert_eq(kser, pser)
                self.assert_eq(kdf, pdf)
                self.assert_eq(ksery, psery)

        with self.assertRaises(ValueError):
            kser.loc["viper"] = -kser

        # multiindex
        pser = pd.Series(
            [1, 2, 3],
            index=pd.MultiIndex.from_tuples([("x", "cobra"), ("x", "viper"), ("y", "sidewinder")]),
        )
        kser = ks.from_pandas(pser)

        pser.loc["x"] = pser * 10
        kser.loc["x"] = kser * 10
        self.assert_eq(kser, pser)

        pser.loc["y"] = pser * 10
        kser.loc["y"] = kser * 10
        self.assert_eq(kser, pser)

        if LooseVersion(pd.__version__) < LooseVersion("1.0"):
            # TODO: seems like a pandas' bug in pandas>=1.0.0?
            pser.loc[("x", "viper"):"y"] = pser * 20
            kser.loc[("x", "viper"):"y"] = kser * 20
            self.assert_eq(kser, pser)

    def test_series_iloc_setitem(self):
        pdf = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]}, index=["cobra", "viper", "sidewinder"])
        kdf = ks.from_pandas(pdf)

        pser = pdf.x
        psery = pdf.y
        kser = kdf.x
        ksery = kdf.y

        piloc = pser.iloc
        kiloc = kser.iloc

        pser1 = pser + 1
        kser1 = kser + 1

        for key, value in [
            ([1, 2], 10),
            (1, 50),
            (slice(None), 10),
            (slice(None, 1), 20),
            (slice(1, None), 30),
        ]:
            with self.subTest(key=key, value=value):
                pser.iloc[key] = value
                kser.iloc[key] = value
                self.assert_eq(kser, pser)
                self.assert_eq(kdf, pdf)
                self.assert_eq(ksery, psery)

                piloc[key] = -value
                kiloc[key] = -value
                self.assert_eq(kser, pser)
                self.assert_eq(kdf, pdf)
                self.assert_eq(ksery, psery)

                pser1.iloc[key] = value
                kser1.iloc[key] = value
                self.assert_eq(kser1, pser1)
                self.assert_eq(kdf, pdf)
                self.assert_eq(ksery, psery)

        with self.assertRaises(ValueError):
            kser.iloc[1] = -kser

        pser = pd.Index([1, 2, 3]).to_series()
        kser = ks.Index([1, 2, 3]).to_series()

        pser1 = pser + 1
        kser1 = kser + 1

        pser.iloc[0] = 10
        kser.iloc[0] = 10
        self.assert_eq(kser, pser)

        pser1.iloc[0] = 20
        kser1.iloc[0] = 20
        self.assert_eq(kser1, pser1)

        pdf = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        kdf = ks.from_pandas(pdf)

        pser = pdf.a
        kser = kdf.a

        pser.iloc[[1]] = -pdf.b
        kser.iloc[[1]] = -kdf.b
        self.assert_eq(kser, pser)
        self.assert_eq(kdf, pdf)

        with self.assertRaisesRegex(ValueError, "Incompatible indexer with DataFrame"):
            kser.iloc[1] = kdf[["b"]]

    def test_iloc_raises(self):
        pdf = pd.DataFrame({"A": [1, 2], "B": [3, 4], "C": [5, 6]})
        kdf = ks.from_pandas(pdf)

        with self.assertRaisesRegex(SparkPandasIndexingError, "Only accepts pairs of candidates"):
            kdf.iloc[[0, 1], [0, 1], [1, 2]]

        with self.assertRaisesRegex(SparkPandasIndexingError, "Too many indexers"):
            kdf.A.iloc[[0, 1], [0, 1]]

        with self.assertRaisesRegex(TypeError, "cannot do slice indexing with these indexers"):
            kdf.iloc[:"b", :]

        with self.assertRaisesRegex(TypeError, "cannot do slice indexing with these indexers"):
            kdf.iloc[:, :"b"]

        with self.assertRaisesRegex(TypeError, "cannot perform reduce with flexible type"):
            kdf.iloc[:, ["A"]]

        with self.assertRaisesRegex(ValueError, "Location based indexing can only have"):
            kdf.iloc[:, "A"]

        with self.assertRaisesRegex(IndexError, "out of range"):
            kdf.iloc[:, [5, 6]]

    def test_index_operator_datetime(self):
        dates = pd.date_range("20130101", periods=6)
        pdf = pd.DataFrame(np.random.randn(6, 4), index=dates, columns=list("ABCD"))
        kdf = ks.from_pandas(pdf)

        # Positional iloc search
        self.assert_eq(kdf[:4], pdf[:4], almost=True)
        self.assert_eq(kdf[:3], pdf[:3], almost=True)
        self.assert_eq(kdf[3:], pdf[3:], almost=True)
        self.assert_eq(kdf[2:], pdf[2:], almost=True)
        self.assert_eq(kdf[2:3], pdf[2:3], almost=True)
        self.assert_eq(kdf[2:-1], pdf[2:-1], almost=True)
        self.assert_eq(kdf[10:3], pdf[10:3], almost=True)

        # Index loc search
        self.assert_eq(kdf.A[4], pdf.A[4])
        self.assert_eq(kdf.A[3], pdf.A[3])

        # Positional iloc search
        self.assert_eq(kdf.A[:4], pdf.A[:4], almost=True)
        self.assert_eq(kdf.A[:3], pdf.A[:3], almost=True)
        self.assert_eq(kdf.A[3:], pdf.A[3:], almost=True)
        self.assert_eq(kdf.A[2:], pdf.A[2:], almost=True)
        self.assert_eq(kdf.A[2:3], pdf.A[2:3], almost=True)
        self.assert_eq(kdf.A[2:-1], pdf.A[2:-1], almost=True)
        self.assert_eq(kdf.A[10:3], pdf.A[10:3], almost=True)

        dt1 = datetime.datetime.strptime("2013-01-02", "%Y-%m-%d")
        dt2 = datetime.datetime.strptime("2013-01-04", "%Y-%m-%d")

        # Index loc search
        self.assert_eq(kdf[:dt2], pdf[:dt2], almost=True)
        self.assert_eq(kdf[dt1:], pdf[dt1:], almost=True)
        self.assert_eq(kdf[dt1:dt2], pdf[dt1:dt2], almost=True)
        self.assert_eq(kdf.A[dt2], pdf.A[dt2], almost=True)
        self.assert_eq(kdf.A[:dt2], pdf.A[:dt2], almost=True)
        self.assert_eq(kdf.A[dt1:], pdf.A[dt1:], almost=True)
        self.assert_eq(kdf.A[dt1:dt2], pdf.A[dt1:dt2], almost=True)

    def test_index_operator_int(self):
        pdf = pd.DataFrame(np.random.randn(6, 4), index=[1, 3, 5, 7, 9, 11], columns=list("ABCD"))
        kdf = ks.from_pandas(pdf)

        # Positional iloc search
        self.assert_eq(kdf[:4], pdf[:4])
        self.assert_eq(kdf[:3], pdf[:3])
        self.assert_eq(kdf[3:], pdf[3:])
        self.assert_eq(kdf[2:], pdf[2:])
        self.assert_eq(kdf[2:3], pdf[2:3])
        self.assert_eq(kdf[2:-1], pdf[2:-1])
        self.assert_eq(kdf[10:3], pdf[10:3])

        # Index loc search
        self.assert_eq(kdf.A[5], pdf.A[5])
        self.assert_eq(kdf.A[3], pdf.A[3])
        with self.assertRaisesRegex(
            NotImplementedError, "Duplicated row selection is not currently supported"
        ):
            kdf.iloc[[1, 1]]

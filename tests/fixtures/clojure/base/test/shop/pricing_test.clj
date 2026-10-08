(ns shop.pricing-test
  (:require [clojure.test :refer [deftest is]]
            [shop.pricing :as pricing]))

(deftest base-price-test
  (is (= 4 (pricing/base-price 2))))
